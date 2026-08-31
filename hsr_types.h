#pragma once
#include <string>
#include <cstdint>
#include <algorithm>
#include <cctype>
#include <cmath>
#include <sstream>
#include <stdexcept>

enum class ScenarioType { METAL, COMPOSITE, REPEATER };
enum class PassiveModelType
{
  LEGACY_SCALAR,
  COMPONENT_BUDGET,
  DECLARED_SCALAR
};
enum class TrafficDirection { DOWNLINK, UPLINK };

inline std::string ScenarioToString(ScenarioType s)
{
  switch (s)
  {
    case ScenarioType::METAL: return "metal";
    case ScenarioType::COMPOSITE: return "composite";
    case ScenarioType::REPEATER: return "repeater";
  }
  return "unknown";
}

inline bool TryParseScenario(const std::string& value, ScenarioType& out)
{
  std::string normalized;
  normalized.reserve(value.size());
  for (char c : value)
  {
    normalized.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
  }

  if (normalized == "metal")
  {
    out = ScenarioType::METAL;
    return true;
  }
  if (normalized == "composite")
  {
    out = ScenarioType::COMPOSITE;
    return true;
  }
  if (normalized == "repeater" || normalized == "velocity-connect" || normalized == "velocity_connect")
  {
    out = ScenarioType::REPEATER;
    return true;
  }
  return false;
}

inline std::string PassiveModelToString(PassiveModelType model)
{
  switch (model)
  {
    case PassiveModelType::LEGACY_SCALAR: return "legacy_scalar";
    case PassiveModelType::COMPONENT_BUDGET: return "component_budget";
    case PassiveModelType::DECLARED_SCALAR: return "declared_scalar";
  }
  return "unknown";
}

inline bool TryParsePassiveModel(const std::string& value, PassiveModelType& out)
{
  std::string normalized;
  normalized.reserve(value.size());
  for (char c : value)
  {
    char lower = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    normalized.push_back(lower == '-' ? '_' : lower);
  }

  if (normalized == "legacy" || normalized == "legacy_scalar")
  {
    out = PassiveModelType::LEGACY_SCALAR;
    return true;
  }
  if (normalized == "component" || normalized == "component_budget")
  {
    out = PassiveModelType::COMPONENT_BUDGET;
    return true;
  }
  if (normalized == "declared" || normalized == "declared_scalar")
  {
    out = PassiveModelType::DECLARED_SCALAR;
    return true;
  }
  return false;
}

inline std::string TrafficDirectionToString(TrafficDirection direction)
{
  switch (direction)
  {
    case TrafficDirection::DOWNLINK: return "downlink";
    case TrafficDirection::UPLINK: return "uplink";
  }
  return "unknown";
}

inline bool TryParseTrafficDirection(const std::string& value, TrafficDirection& out)
{
  std::string normalized;
  normalized.reserve(value.size());
  for (char c : value)
  {
    normalized.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
  }

  if (normalized == "downlink" || normalized == "dl")
  {
    out = TrafficDirection::DOWNLINK;
    return true;
  }
  if (normalized == "uplink" || normalized == "ul")
  {
    out = TrafficDirection::UPLINK;
    return true;
  }
  return false;
}

struct PassiveLinkBudget
{
  double feederLossDb{0.0};
  double couplingLossDb{0.0};
  double indoorPathLossDb{0.0};
  double donorGainDbi{0.0};
  double serviceGainDbi{0.0};
  double networkLossDb{0.0};
  double apertureGainDb{0.0};
  double equivalentLossDb{0.0};
};

struct RunConfig
{
  std::string outDir{"out"};

  // NR
  double carrierHz{3.5e9};
  double bandwidthHz{100e6};
  uint16_t numerology{0};
  double gnbTxPowerDbm{40.0};
  double ueTxPowerDbm{23.0};
  double ueNoiseFigureDb{7.0};

  // 5G-LENA channel helper strings
  std::string nrScenario{"UMi"};
  std::string nrCondition{"LOS"};
  std::string nrChannelModel{"ThreeGpp"};
  bool shadowingEnabled{false};

  // SRS remains configurable. The transaction-v2 campaign records the
  // selected mode explicitly so disabled-SRS evidence cannot be mistaken for
  // a fully configured uplink sounding study.
  bool enableSrs{false};

  // Geometry / motion
  double gnbHeight{10.0};
  double gnbLateralOffsetM{0.0};
  double ueHeight{1.5};
  double speedKmph{300.0};
  double distanceM{500.0};

  // Multi-cell railway corridor. The submitted-paper profile keeps one gNB.
  uint32_t numGnbs{1};
  double gnbSpacingM{1000.0};
  bool guardedCorridor{false};
  bool enableHandover{false};
  std::string handoverAlgorithm{"ns3::NrA3RsrpHandoverAlgorithm"};
  double handoverHysteresisDb{1.5};
  uint32_t handoverTimeToTriggerMs{128};
  // Legacy runs used ideal RRC. The transaction-v2 campaign exercises
  // non-ideal RRC and records the mode in every accepted row.
  bool useIdealRrc{true};

  // Time
  double simTimeS{2.0};
  double appStartS{0.2};
  // A non-positive value means "stop with the simulator".
  double appStopS{0.0};
  // Zero preserves the static channel realization used by the legacy profile.
  double channelUpdatePeriodMs{0.0};

  // Traffic
  uint32_t numUes{1};
  uint32_t appPktSizeBytes{1024};

  bool saturatingLoad{true};
  double perUeOfferedMbps{8.19};
  double saturatingIntervalUs{100.0};
  TrafficDirection trafficDirection{TrafficDirection::DOWNLINK};

  // Scenario
  ScenarioType scenario{ScenarioType::REPEATER};
  PassiveModelType passiveModel{PassiveModelType::COMPONENT_BUDGET};

  // Baseline VPL
  double metalVplDb{60.0};
  double compositeVplDb{20.0};
  double legacyRepeaterLossDb{5.0};
  // A predeclared end-to-end scalar hypothesis. It is not decomposed into
  // antenna gain or feedthrough components and is not inferred from HFSS.
  double declaredPassiveLossDb{6.5};

  // Velocity Connect passive repeater link budget
  double donorGainDbi{8.0};
  double serviceGainDbi{2.0};
  double feederCableLossDb{3.0};
  double indoorDistribLossDb{4.0};
  double couplingLossDb{8.0};

  // RNG
  uint64_t seed{1};
  uint64_t run{1};

  // Scheduler
  std::string schedulerType{"ns3::NrMacSchedulerOfdmaPF"};

  // Logs
  bool verbose{false};
};

inline void RequireFiniteNonNegative(const char* name, double value)
{
  if (!std::isfinite(value) || value < 0.0)
  {
    std::ostringstream message;
    message << name << " must be finite and non-negative; received " << value;
    throw std::invalid_argument(message.str());
  }
}

inline void RequireFinite(const char* name, double value)
{
  if (!std::isfinite(value))
  {
    std::ostringstream message;
    message << name << " must be finite; received " << value;
    throw std::invalid_argument(message.str());
  }
}

inline void RequireFinitePositive(const char* name, double value)
{
  if (!std::isfinite(value) || value <= 0.0)
  {
    std::ostringstream message;
    message << name << " must be finite and positive; received " << value;
    throw std::invalid_argument(message.str());
  }
}

inline PassiveLinkBudget ComputePassiveLinkBudget(const RunConfig& cfg)
{
  PassiveLinkBudget budget;
  budget.feederLossDb = cfg.feederCableLossDb;
  budget.couplingLossDb = cfg.couplingLossDb;
  budget.indoorPathLossDb = cfg.indoorDistribLossDb;
  budget.donorGainDbi = cfg.donorGainDbi;
  budget.serviceGainDbi = cfg.serviceGainDbi;

  // Energy-consistent equivalent system-level abstraction:
  // L_eq = (L_feeder + L_coupling) + L_indoor - (G_donor + G_service).
  // L_indoor appears exactly once. Every term is retained in result provenance.
  budget.networkLossDb = budget.feederLossDb + budget.couplingLossDb;
  budget.apertureGainDb = budget.donorGainDbi + budget.serviceGainDbi;
  budget.equivalentLossDb =
    budget.networkLossDb + budget.indoorPathLossDb - budget.apertureGainDb;
  return budget;
}

inline void ValidateRunConfig(const RunConfig& cfg)
{
  RequireFinitePositive("carrierHz", cfg.carrierHz);
  RequireFinitePositive("bandwidthHz", cfg.bandwidthHz);
  RequireFinitePositive("gnbHeight", cfg.gnbHeight);
  RequireFiniteNonNegative("gnbLateralOffsetM", cfg.gnbLateralOffsetM);
  RequireFinitePositive("ueHeight", cfg.ueHeight);
  RequireFinite("gnbTxPowerDbm", cfg.gnbTxPowerDbm);
  RequireFinite("ueTxPowerDbm", cfg.ueTxPowerDbm);
  RequireFiniteNonNegative("ueNoiseFigureDb", cfg.ueNoiseFigureDb);
  RequireFiniteNonNegative("gnbHeight", cfg.gnbHeight);
  RequireFiniteNonNegative("ueHeight", cfg.ueHeight);
  RequireFiniteNonNegative("speedKmph", cfg.speedKmph);
  RequireFiniteNonNegative("distanceM", cfg.distanceM);
  RequireFinitePositive("simTimeS", cfg.simTimeS);
  RequireFiniteNonNegative("appStartS", cfg.appStartS);
  RequireFinite("appStopS", cfg.appStopS);
  RequireFiniteNonNegative("channelUpdatePeriodMs", cfg.channelUpdatePeriodMs);
  RequireFiniteNonNegative("perUeOfferedMbps", cfg.perUeOfferedMbps);
  RequireFiniteNonNegative("saturatingIntervalUs", cfg.saturatingIntervalUs);
  RequireFiniteNonNegative("metalVplDb", cfg.metalVplDb);
  RequireFiniteNonNegative("compositeVplDb", cfg.compositeVplDb);
  RequireFiniteNonNegative("legacyRepeaterLossDb", cfg.legacyRepeaterLossDb);
  RequireFiniteNonNegative("declaredPassiveLossDb", cfg.declaredPassiveLossDb);
  RequireFiniteNonNegative("donorGainDbi", cfg.donorGainDbi);
  RequireFiniteNonNegative("serviceGainDbi", cfg.serviceGainDbi);
  RequireFiniteNonNegative("feederCableLossDb", cfg.feederCableLossDb);
  RequireFiniteNonNegative("indoorDistribLossDb", cfg.indoorDistribLossDb);
  RequireFiniteNonNegative("couplingLossDb", cfg.couplingLossDb);
  RequireFiniteNonNegative("gnbSpacingM", cfg.gnbSpacingM);
  RequireFiniteNonNegative("handoverHysteresisDb", cfg.handoverHysteresisDb);

  if (cfg.numerology > 5)
  {
    throw std::invalid_argument("numerology must be between 0 and 5");
  }
  if (cfg.numUes < 1)
  {
    throw std::invalid_argument("numUes must be at least 1");
  }
  if (cfg.appPktSizeBytes < 1)
  {
    throw std::invalid_argument("appPktSizeBytes must be at least 1");
  }
  if (cfg.appStartS >= cfg.simTimeS)
  {
    throw std::invalid_argument("appStartS must be less than simTimeS");
  }
  const double appStopS = cfg.appStopS > 0.0 ? cfg.appStopS : cfg.simTimeS;
  if (appStopS <= cfg.appStartS || appStopS > cfg.simTimeS)
  {
    throw std::invalid_argument(
      "resolved appStopS must be greater than appStartS and no later than simTimeS");
  }
  if (cfg.saturatingLoad && cfg.saturatingIntervalUs <= 0.0)
  {
    throw std::invalid_argument("saturatingIntervalUs must be positive");
  }
  if (!cfg.saturatingLoad && cfg.perUeOfferedMbps <= 0.0)
  {
    throw std::invalid_argument("perUeOfferedMbps must be positive");
  }
  if (cfg.numGnbs < 1)
  {
    throw std::invalid_argument("numGnbs must be at least 1");
  }
  if (cfg.enableHandover && cfg.numGnbs < 2)
  {
    throw std::invalid_argument("enableHandover requires at least two gNBs");
  }
  if (cfg.enableHandover && cfg.gnbSpacingM <= 0.0)
  {
    throw std::invalid_argument("enableHandover requires positive gnbSpacingM");
  }
  if (cfg.guardedCorridor)
  {
    if (cfg.speedKmph <= 0.0)
    {
      throw std::invalid_argument("guardedCorridor requires positive speedKmph");
    }
    if (cfg.numGnbs < 6)
    {
      throw std::invalid_argument("guardedCorridor requires at least six gNBs");
    }
  }
  if (cfg.handoverAlgorithm != "ns3::NrA3RsrpHandoverAlgorithm")
  {
    throw std::invalid_argument(
      "Only ns3::NrA3RsrpHandoverAlgorithm is validated by this project");
  }

  if (cfg.passiveModel == PassiveModelType::COMPONENT_BUDGET)
  {
    const PassiveLinkBudget budget = ComputePassiveLinkBudget(cfg);
    if (!std::isfinite(budget.equivalentLossDb) || budget.equivalentLossDb < 0.0)
    {
      std::ostringstream message;
      message
        << "The component budget produces unsupported net passive gain ("
        << budget.equivalentLossDb
        << " dB). Increase measured losses or use an explicit calibrated gain model.";
      throw std::invalid_argument(message.str());
    }
  }
}

inline double ResolveApplicationStopS(const RunConfig& cfg)
{
  return cfg.appStopS > 0.0 ? cfg.appStopS : cfg.simTimeS;
}

// Define a spatially matched interior measurement window. The UE starts at
// x=0, traffic is measured only from 1.75*ISD to 3.75*ISD, and simulation
// continues to 4*ISD for a guard/cool-down segment. Six sites at 0..5*ISD
// ensure that the measured interval cannot run beyond the final site.
inline void ApplyGuardedCorridorWindow(RunConfig& cfg)
{
  if (!cfg.guardedCorridor)
  {
    return;
  }
  if (cfg.speedKmph <= 0.0 || cfg.gnbSpacingM <= 0.0)
  {
    throw std::invalid_argument(
      "guardedCorridor requires positive speedKmph and gnbSpacingM");
  }
  const double speedMps = cfg.speedKmph / 3.6;
  cfg.distanceM = 0.0;
  cfg.appStartS = 1.75 * cfg.gnbSpacingM / speedMps;
  cfg.appStopS = 3.75 * cfg.gnbSpacingM / speedMps;
  cfg.simTimeS = 4.0 * cfg.gnbSpacingM / speedMps;
}

inline double ComputeEffectivePenetrationLossDb(const RunConfig& cfg)
{
  if (cfg.scenario == ScenarioType::METAL) return cfg.metalVplDb;
  if (cfg.scenario == ScenarioType::COMPOSITE) return cfg.compositeVplDb;
  if (cfg.passiveModel == PassiveModelType::LEGACY_SCALAR)
  {
    return cfg.legacyRepeaterLossDb;
  }
  if (cfg.passiveModel == PassiveModelType::DECLARED_SCALAR)
  {
    return cfg.declaredPassiveLossDb;
  }
  return ComputePassiveLinkBudget(cfg).equivalentLossDb;
}

inline double ComputeSubcarrierSpacingKHz(uint16_t numerology)
{
  return 15.0 * static_cast<double>(1u << numerology);
}

// Apply the submitted-paper baseline before command-line overrides are parsed.
// This keeps the paper profile explicit while allowing every value to remain
// independently configurable from the command line.
inline void ApplyPaperProfile(RunConfig& cfg)
{
  cfg.carrierHz = 3.5e9;
  cfg.bandwidthHz = 100e6;
  cfg.numerology = 1;
  cfg.gnbTxPowerDbm = 40.0;
  cfg.ueTxPowerDbm = 23.0;
  cfg.ueNoiseFigureDb = 7.0;
  cfg.nrScenario = "UMi";
  cfg.nrCondition = "LOS";
  cfg.nrChannelModel = "ThreeGpp";
  cfg.shadowingEnabled = false;

  cfg.speedKmph = 300.0;
  cfg.distanceM = 500.0;
  cfg.simTimeS = 2.0;
  cfg.appStartS = 0.2;

  cfg.numUes = 10;
  cfg.appPktSizeBytes = 1024;
  cfg.saturatingLoad = false;
  cfg.perUeOfferedMbps = 8.19;
  cfg.saturatingIntervalUs = 100.0;

  cfg.metalVplDb = 60.0;
  cfg.compositeVplDb = 20.0;
  cfg.legacyRepeaterLossDb = 5.0;
  cfg.declaredPassiveLossDb = 6.5;
  cfg.donorGainDbi = 8.0;
  cfg.serviceGainDbi = 2.0;
  cfg.feederCableLossDb = 3.0;
  cfg.couplingLossDb = 8.0;
  cfg.indoorDistribLossDb = 4.0;

  // Preserve the submitted single-cell experiment as a reproducibility
  // baseline. Advanced corridor experiments opt into multiple gNBs explicitly.
  cfg.numGnbs = 1;
  cfg.enableHandover = false;
}
