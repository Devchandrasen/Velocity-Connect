#pragma once
#include <functional>
#include <vector>
#include <string>
#include <memory>
#include <set>

#include "ns3/core-module.h"
#include "ns3/nr-module.h"
#include "hsr_types.h"
#include "hsr_io.h"
#include "ns3/spectrum-signal-parameters.h"
#include "ns3/spectrum-propagation-loss-model.h"
#include "ns3/isotropic-antenna-model.h"
#include "ns3/three-gpp-spectrum-propagation-loss-model.h"
#include "ns3/three-gpp-propagation-loss-model.h"

using namespace ns3;

// Non-phased replacement channel. It deliberately does not populate a MIMO
// channel matrix: one declared Jones projection becomes one received PSD.
class HsrEmSpectrumLossModel : public SpectrumPropagationLossModel
{
public:
  static TypeId GetTypeId()
  {
    static TypeId tid = TypeId("ns3::HsrEmSpectrumLossModel")
      .SetParent<SpectrumPropagationLossModel>().AddConstructor<HsrEmSpectrumLossModel>();
    return tid;
  }
  void Setup(std::shared_ptr<const hsr::em::Bridge> bridge,
             Ptr<const MobilityModel> gnb, Ptr<const MobilityModel> ue, const std::string& outDir)
  {
    m_bridge = std::move(bridge); m_gnb = gnb; m_ue = ue; m_outDir = outDir;
    if (!outDir.empty()) WriteCsvHeader(outDir+"/em_bridge_bands.csv",
      "direction,frequency_hz,low_hz,high_hz,amplitude_re,amplitude_im,power_gain,first_tx_psd_w_hz,first_rx_psd_w_hz");
  }
  void WriteRuntimeAudit() const
  {
    WriteCsvHeader(m_outDir+"/em_bridge_runtime.csv", "dl_channel_calls,ul_channel_calls,band_evaluations");
    AppendCsvLine(m_outDir+"/em_bridge_runtime.csv",
      std::to_string(m_dlCalls)+","+std::to_string(m_ulCalls)+","+std::to_string(m_evaluations));
  }
private:
  int64_t DoAssignStreams(int64_t) override { return 0; }
  Ptr<SpectrumValue> DoCalcRxPowerSpectralDensity(Ptr<const SpectrumSignalParameters> params,
    Ptr<const MobilityModel> a, Ptr<const MobilityModel> b) const override
  {
    hsr::em::Require(bool(m_bridge), "channel not configured");
    if ((a == m_gnb && b == m_gnb) || (a == m_ue && b == m_ue))
      return Create<SpectrumValue>(*params->psd); // Same-role link: no coach crossing.
    const bool reverse = a == m_ue && b == m_gnb;
    hsr::em::Require(reverse || (a == m_gnb && b == m_ue), "unknown link lacks installed operators");
    // Fail if actual geometry drifts, even when the caller bypasses CLI validation.
    for (const auto& item : {std::make_pair(m_gnb,m_bridge->installation.gnb),
                            std::make_pair(m_ue,m_bridge->installation.ue)})
    {
      const auto p = item.first->GetPosition();
      const auto& expected = item.second;
      hsr::em::Require(std::abs(p.x-expected[0]) < 1e-7 && std::abs(p.y-expected[1]) < 1e-7 &&
                      std::abs(p.z-expected[2]) < 1e-7, "installed operator geometry mismatch");
    }
    reverse ? ++m_ulCalls : ++m_dlCalls;
    auto result = Create<SpectrumValue>(*params->psd);
    auto band = result->ConstBandsBegin();
    for (auto v = result->ValuesBegin(); v != result->ValuesEnd(); ++v,++band)
    {
      (void)hsr::em::Interval(m_bridge->fixture.samples,band->fl);
      (void)hsr::em::Interval(m_bridge->fixture.samples,band->fh);
      (void)hsr::em::Interval(m_bridge->installation.samples,band->fl);
      (void)hsr::em::Interval(m_bridge->installation.samples,band->fh);
      const auto amplitude = m_bridge->Amplitude(band->fc,reverse);
      const double inputPsd = *v;
      *v *= std::norm(amplitude);
      ++m_evaluations;
      if (!m_outDir.empty() && inputPsd > 0 && m_seen.emplace(reverse,band->fc).second)
      {
        std::ostringstream row;
        row << std::setprecision(17) << (reverse ? "uplink" : "downlink") << ',' << band->fc << ','
            << band->fl << ',' << band->fh << ',' << amplitude.real() << ',' << amplitude.imag() << ','
            << std::norm(amplitude) << ',' << inputPsd << ',' << *v;
        AppendCsvLine(m_outDir+"/em_bridge_bands.csv",row.str());
      }
    }
    return result;
  }
  std::shared_ptr<const hsr::em::Bridge> m_bridge;
  Ptr<const MobilityModel> m_gnb, m_ue;
  std::string m_outDir;
  mutable std::set<std::pair<bool,double>> m_seen;
  mutable uint64_t m_dlCalls{0},m_ulCalls{0},m_evaluations{0};
};

inline void ConfigureNrHelper(Ptr<NrHelper> nrHelper, const RunConfig& cfg)
{
  nrHelper->SetAttribute("UseIdealRrc", BooleanValue(cfg.useIdealRrc));
  nrHelper->SetGnbPhyAttribute("Numerology", UintegerValue(cfg.numerology));
  if (cfg.passiveModel == PassiveModelType::EM_COMPLEX)
  {
    nrHelper->SetAttribute("CsiFeedbackFlags", UintegerValue(CQI_PDSCH_SISO));
    for (const auto* name : {"NumRows","NumColumns","NumHorizontalPorts","NumVerticalPorts"})
    {
      nrHelper->SetGnbAntennaAttribute(name,UintegerValue(1));
      nrHelper->SetUeAntennaAttribute(name,UintegerValue(1));
    }
    nrHelper->SetGnbAntennaAttribute("IsDualPolarized",BooleanValue(false));
    nrHelper->SetUeAntennaAttribute("IsDualPolarized",BooleanValue(false));
    nrHelper->SetGnbAntennaAttribute("AntennaElement",PointerValue(CreateObject<IsotropicAntennaModel>()));
    nrHelper->SetUeAntennaAttribute("AntennaElement",PointerValue(CreateObject<IsotropicAntennaModel>()));
  }

  if (cfg.enableHandover)
  {
    nrHelper->SetHandoverAlgorithmType(cfg.handoverAlgorithm);
    nrHelper->SetHandoverAlgorithmAttribute(
      "Hysteresis", DoubleValue(cfg.handoverHysteresisDb));
    nrHelper->SetHandoverAlgorithmAttribute(
      "TimeToTrigger", TimeValue(MilliSeconds(cfg.handoverTimeToTriggerMs)));
  }
  else
  {
    nrHelper->SetHandoverAlgorithmType("ns3::NrNoOpHandoverAlgorithm");
  }

  // Scheduler TypeId (fail-safe)
  TypeId schedTid;
  bool ok = TypeId::LookupByNameFailSafe(cfg.schedulerType, &schedTid);
  if (ok)
  {
    nrHelper->SetSchedulerTypeId(schedTid);
  }
  else
  {
    NS_LOG_UNCOND("WARNING: Scheduler not found: " << cfg.schedulerType << " (using default)");
  }

  // When SRS is disabled, make the scheduler state explicit instead of
  // relying on release-specific defaults. Enabled-SRS scalability is tested
  // separately before it can become part of an accepted campaign contract.
  if (!cfg.enableSrs)
  {
    nrHelper->SetSchedulerAttribute("EnableSrsInUlSlots", BooleanValue(false));
    nrHelper->SetSchedulerAttribute("EnableSrsInFSlots", BooleanValue(false));
    nrHelper->SetSchedulerAttribute("SrsSymbols", UintegerValue(0));
  }
}

// Create and assign spectrum channels using NrChannelHelper
inline Ptr<HsrEmSpectrumLossModel> ConfigureAndAssignChannels(const RunConfig& cfg,
  std::vector<std::reference_wrapper<OperationBandInfo>>& opBands,
  const NodeContainer& gnbNodes, const NodeContainer& ueNodes)
{
  if (cfg.passiveModel == PassiveModelType::EM_COMPLEX)
  {
    auto bridge = std::make_shared<hsr::em::Bridge>(cfg.emTouchstonePath,cfg.emOperatorsPath,cfg.emMapping);
    bridge->ValidateRange(cfg.carrierHz-cfg.bandwidthHz/2,cfg.carrierHz+cfg.bandwidthHz/2);
    WriteEmBridgeAudit(cfg,*bridge);
    auto ch = CreateObject<NrChannelHelper>();
    ch->AssignChannelsToBands(opBands,0); // No stock pathloss OR fading; absolute external operators.
    auto bwps = CcBwpCreator::GetAllBwps(opBands);
    hsr::em::Require(bwps.size() == 1, "only one BWP is supported");
    auto model = CreateObject<HsrEmSpectrumLossModel>();
    model->Setup(bridge,gnbNodes.Get(0)->GetObject<MobilityModel>(),
                 ueNodes.Get(0)->GetObject<MobilityModel>(),cfg.outDir);
    bwps[0].get()->GetChannel()->AddSpectrumPropagationLossModel(model);
    return model;
  }
  Config::SetDefault(
    "ns3::ThreeGppChannelModel::UpdatePeriod",
    TimeValue(MilliSeconds(cfg.channelUpdatePeriodMs)));
  Ptr<NrChannelHelper> ch = CreateObject<NrChannelHelper>();
  ch->ConfigureFactories(cfg.nrScenario, cfg.nrCondition, cfg.nrChannelModel);
  ch->SetPathlossAttribute("ShadowingEnabled", BooleanValue(cfg.shadowingEnabled));
  ch->AssignChannelsToBands(opBands);
  return nullptr;
}

inline int64_t AssignExplicitChannelStreams(const RunConfig& cfg,
  const BandwidthPartInfoPtrVector& bwps)
{
  if (cfg.channelRngStream < 0) return 0;
  int64_t current = cfg.channelRngStream;
  std::set<const SpectrumChannel*> seen;
  for (const auto& bwp : bwps)
  {
    auto ch = bwp.get()->GetChannel();
    if (!seen.insert(PeekPointer(ch)).second) continue;
    auto path = DynamicCast<ThreeGppPropagationLossModel>(ch->GetPropagationLossModel());
    auto spec = DynamicCast<ThreeGppSpectrumPropagationLossModel>(ch->GetPhasedArraySpectrumPropagationLossModel());
    hsr::em::Require(path && spec, "explicit channel streams currently require ThreeGpp");
    current += path->AssignStreams(current);
    current += path->GetChannelConditionModel()->AssignStreams(current);
    auto matrix = DynamicCast<ThreeGppChannelModel>(spec->GetChannelModel());
    hsr::em::Require(bool(matrix), "missing ThreeGpp channel matrix RNG");
    current += matrix->AssignStreams(current);
  }
  return current-cfg.channelRngStream;
}
