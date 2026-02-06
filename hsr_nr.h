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

  // ---- CRITICAL FIX for your crash during scalability runs ----
  // Disable SRS scheduling for downlink-focused evaluation (avoids NrGnbPhy allocation-stats assert).
  // These attributes exist in NR scheduler base classes in 5G-LENA.
  if (!cfg.enableSrs)
  {
    nrHelper->SetSchedulerAttribute("EnableSrsInUlSlots", BooleanValue(false));
    nrHelper->SetSchedulerAttribute("EnableSrsInFSlots", BooleanValue(false));
    nrHelper->SetSchedulerAttribute("SrsSymbols", UintegerValue(0));
  }
  // ------------------------------------------------------------
}

// Create and assign spectrum channels using NrChannelHelper
inline void ConfigureAndAssignChannels(const RunConfig& cfg,
                                       std::vector<std::reference_wrapper<OperationBandInfo>>& opBands)
{
  Ptr<NrChannelHelper> ch = CreateObject<NrChannelHelper>();
  ch->ConfigureFactories(cfg.nrScenario, cfg.nrCondition, cfg.nrChannelModel);
  ch->SetPathlossAttribute("ShadowingEnabled", BooleanValue(cfg.shadowingEnabled));
  ch->AssignChannelsToBands(opBands);
}
