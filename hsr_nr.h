#pragma once

#include <functional>
#include <vector>

#include "ns3/core-module.h"
#include "ns3/nr-module.h"
#include "hsr_types.h"

using namespace ns3;

inline void ConfigureNrHelper(Ptr<NrHelper> nrHelper, const RunConfig& cfg)
{
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

    if (!cfg.enableSrs)
    {
        nrHelper->SetSchedulerAttribute("EnableSrsInUlSlots", BooleanValue(false));
        nrHelper->SetSchedulerAttribute("EnableSrsInFSlots", BooleanValue(false));
        nrHelper->SetSchedulerAttribute("SrsSymbols", UintegerValue(0));
    }

    // Stability fix: extreme outage metal case causes HARQ scheduler assert
    if (cfg.scenario == ScenarioType::METAL)
    {
        nrHelper->SetSchedulerAttribute("EnableHarqReTx", BooleanValue(false));
    }
    else
    {
        nrHelper->SetSchedulerAttribute("EnableHarqReTx", BooleanValue(true));
    }
}

inline void ConfigureAndAssignChannels(
    const RunConfig& cfg,
    std::vector<std::reference_wrapper<OperationBandInfo>>& opBands)
{
    Ptr<NrChannelHelper> ch = CreateObject<NrChannelHelper>();
    ch->ConfigureFactories(cfg.nrScenario, cfg.nrCondition, cfg.nrChannelModel);
    ch->SetPathlossAttribute("ShadowingEnabled", BooleanValue(cfg.shadowingEnabled));
    ch->AssignChannelsToBands(opBands);
}
