#pragma once
#include <string>
#include <cstdint>
#include <algorithm>
#include <cctype>

enum class ScenarioType { METAL, COMPOSITE, REPEATER };

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

struct RunConfig
{
  std::string outDir{"out"};

  // NR
  double carrierHz{3.5e9};
  double bandwidthHz{100e6};
  uint16_t numerology{0};
  double gnbTxPowerDbm{40.0};
  double ueNoiseFigureDb{7.0};

  // 5G-LENA channel helper strings
  std::string nrScenario{"UMi"};
  std::string nrCondition{"LOS"};
  std::string nrChannelModel{"ThreeGpp"};
  bool shadowingEnabled{false};

  // ✅ SRS: keep OFF by default to avoid scalability assert
  bool enableSrs{false};

  // Geometry / motion
  double gnbHeight{25.0};
  double ueHeight{1.5};
  double speedKmph{300.0};
  double distanceM{500.0};

  // Time
  double simTimeS{2.0};
  double appStartS{0.2};

  // Traffic
  uint32_t numUes{1};
  uint32_t appPktSizeBytes{1024};

  bool saturatingLoad{true};
  double perUeOfferedMbps{8.19};
  double saturatingIntervalUs{100.0};

  // Scenario
  ScenarioType scenario{ScenarioType::REPEATER};

  // Baseline VPL
  double metalVplDb{60.0};
  double compositeVplDb{20.0};

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

inline double ComputeEffectivePenetrationLossDb(const RunConfig& cfg)
{
  if (cfg.scenario == ScenarioType::METAL) return cfg.metalVplDb;
  if (cfg.scenario == ScenarioType::COMPOSITE) return cfg.compositeVplDb;

  // L_eff = coupling + cable + indoor - (donor + service)
  double leff = cfg.couplingLossDb
              + cfg.feederCableLossDb
              + cfg.indoorDistribLossDb
              - (cfg.donorGainDbi + cfg.serviceGainDbi);

  return std::max(0.0, leff);
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
  cfg.donorGainDbi = 8.0;
  cfg.serviceGainDbi = 2.0;
  cfg.feederCableLossDb = 3.0;
  cfg.couplingLossDb = 8.0;
  cfg.indoorDistribLossDb = 4.0;
}
