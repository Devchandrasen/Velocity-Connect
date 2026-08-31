#pragma once
#include <functional>
#include <vector>
#include <string>

#include "ns3/core-module.h"
#include "ns3/nr-module.h"
#include "hsr_types.h"

using namespace ns3;

inline void ConfigureNrHelper(Ptr<NrHelper> nrHelper, const RunConfig& cfg)
{
  nrHelper->SetAttribute("UseIdealRrc", BooleanValue(cfg.useIdealRrc));
  nrHelper->SetGnbPhyAttribute("Numerology", UintegerValue(cfg.numerology));

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
inline void ConfigureAndAssignChannels(const RunConfig& cfg,
                                       std::vector<std::reference_wrapper<OperationBandInfo>>& opBands)
{
  Config::SetDefault(
    "ns3::ThreeGppChannelModel::UpdatePeriod",
    TimeValue(MilliSeconds(cfg.channelUpdatePeriodMs)));
  Ptr<NrChannelHelper> ch = CreateObject<NrChannelHelper>();
  ch->ConfigureFactories(cfg.nrScenario, cfg.nrCondition, cfg.nrChannelModel);
  ch->SetPathlossAttribute("ShadowingEnabled", BooleanValue(cfg.shadowingEnabled));
  ch->AssignChannelsToBands(opBands);
}
