#include "ns3/core-module.h"
#include "hsr/hsr_runner.h"
#include "hsr/hsr_types.h"
#include "hsr/hsr_io.h"
#include "hsr/hsr_stats.h"

#include <algorithm>
#include <cctype>
#include <iomanip>
#include <sstream>
#include <string>

using namespace ns3;

static ScenarioType ParseScenario(const std::string& s)
{
    std::string x = s;
    std::transform(x.begin(), x.end(), x.begin(),
                   [](unsigned char c) { return std::tolower(c); });

    if (x == "metal") return ScenarioType::METAL;
    if (x == "composite") return ScenarioType::COMPOSITE;
    if (x == "repeater" || x == "velocity" || x == "velocity_connect")
        return ScenarioType::REPEATER;

    NS_FATAL_ERROR("Unknown scenario string: " << s
                   << ". Use metal / composite / repeater");
    return ScenarioType::REPEATER;
}

int main(int argc, char* argv[])
{
    RunConfig cfg;
    std::string scenarioStr = "repeater";

    CommandLine cmd;
    cmd.AddValue("outDir", "Output directory", cfg.outDir);

    cmd.AddValue("scenario", "metal/composite/repeater", scenarioStr);
    cmd.AddValue("simTime", "Simulation time (s)", cfg.simTimeS);
    cmd.AddValue("appStart", "Application start time (s)", cfg.appStartS);

    cmd.AddValue("seed", "RNG seed", cfg.seed);
    cmd.AddValue("run", "RNG run", cfg.run);

    cmd.AddValue("distance", "Distance (m)", cfg.distanceM);
    cmd.AddValue("speed", "Speed (km/h)", cfg.speedKmph);

    cmd.AddValue("numUes", "Number of UEs", cfg.numUes);
    cmd.AddValue("appPktSizeBytes", "Application packet size (bytes)", cfg.appPktSizeBytes);

    cmd.AddValue("nrScenario", "NR scenario string (UMi/RMa/UMa/etc.)", cfg.nrScenario);
    cmd.AddValue("nrCondition", "NR condition (LOS/NLOS/Default)", cfg.nrCondition);
    cmd.AddValue("nrChannelModel", "NR channel model (ThreeGpp/TwoRay/NYU)", cfg.nrChannelModel);
    cmd.AddValue("shadowing", "Enable shadowing (0/1)", cfg.shadowingEnabled);

    cmd.AddValue("scheduler", "Scheduler TypeId string", cfg.schedulerType);
    cmd.AddValue("enableSrs", "Enable SRS scheduling (0/1)", cfg.enableSrs);

    cmd.AddValue("gnbTxPowerDbm", "gNB Tx power (dBm)", cfg.gnbTxPowerDbm);
    cmd.AddValue("ueNoiseFigureDb", "UE noise figure (dB)", cfg.ueNoiseFigureDb);

    cmd.AddValue("saturatingLoad", "Use saturating traffic (0/1)", cfg.saturatingLoad);
    cmd.AddValue("perUeOfferedMbps", "Per-UE offered load (Mbps)", cfg.perUeOfferedMbps);
    cmd.AddValue("saturatingIntervalUs", "Saturating inter-packet interval (us)", cfg.saturatingIntervalUs);

    cmd.AddValue("metalVplDb", "Metal coach VPL (dB)", cfg.metalVplDb);
    cmd.AddValue("compositeVplDb", "Composite coach VPL (dB)", cfg.compositeVplDb);

    cmd.AddValue("donorGainDbi", "Donor antenna gain (dBi)", cfg.donorGainDbi);
    cmd.AddValue("serviceGainDbi", "Service antenna gain (dBi)", cfg.serviceGainDbi);
    cmd.AddValue("feederCableLossDb", "Feeder coax loss (dB)", cfg.feederCableLossDb);
    cmd.AddValue("indoorDistribLossDb", "Indoor distribution loss (dB)", cfg.indoorDistribLossDb);
    cmd.AddValue("couplingLossDb", "Coupler/mismatch/connector loss (dB)", cfg.couplingLossDb);

    cmd.AddValue("verbose", "Print effective-loss breakdown (0/1)", cfg.verbose);
    cmd.Parse(argc, argv);

    cfg.scenario = ParseScenario(scenarioStr);

    EnsureDir(cfg.outDir);

    Metrics m = RunOnce(cfg);
    double effLoss = ComputeEffectivePenetrationLossDb(cfg);

    std::string csvPath = cfg.outDir + "/single_result.csv";
    WriteCsvHeader(csvPath,
                   "scenario,speed_kmph,distance_m,num_ues,eff_loss_db,throughput_mbps,pdr,tx_pkts,rx_pkts,mean_lat_ms,p50_lat_ms,p95_lat_ms,jain_fairness");

    std::ostringstream line;
    line << ScenarioToString(cfg.scenario) << ","
         << cfg.speedKmph << ","
         << cfg.distanceM << ","
         << cfg.numUes << ","
         << effLoss << ","
         << std::fixed << std::setprecision(6)
         << m.throughputMbps << ","
         << m.pdr << ","
         << m.txPackets << ","
         << m.rxPackets << ","
         << m.meanLatMs << ","
         << m.p50LatMs << ","
         << m.p95LatMs << ","
         << m.jainFairness;

    AppendCsvLine(csvPath, line.str());

    std::cout << "single_result.csv saved in: " << csvPath << std::endl;
    return 0;
}
