#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <functional>
#include <iomanip>
#include <limits>
#include <numeric>
#include <sstream>
#include <string>
#include <vector>

#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/internet-module.h"
#include "ns3/mobility-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/nr-module.h"

#include "hsr_types.h"
#include "hsr_io.h"
#include "hsr_apps.h"
#include "hsr_stats.h"
#include "hsr_nr.h"

using namespace ns3;

inline Metrics RunOnce(RunConfig cfg)
{
    Metrics out;

    RngSeedManager::SetSeed(cfg.seed);
    RngSeedManager::SetRun(cfg.run);

    NodeContainer gnbNodes, ueNodes, remoteHostContainer;
    gnbNodes.Create(1);
    ueNodes.Create(cfg.numUes);
    remoteHostContainer.Create(1);
    Ptr<Node> remoteHost = remoteHostContainer.Get(0);

    MobilityHelper gnbMob;
    gnbMob.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    gnbMob.Install(gnbNodes);
    gnbNodes.Get(0)->GetObject<ConstantPositionMobilityModel>()->SetPosition(
        Vector(0.0, 0.0, cfg.gnbHeight));

    MobilityHelper ueMob;
    ueMob.SetMobilityModel("ns3::ConstantVelocityMobilityModel");
    ueMob.Install(ueNodes);

    double vms = (cfg.speedKmph * 1000.0) / 3600.0;
    for (uint32_t u = 0; u < ueNodes.GetN(); ++u)
    {
        auto cv = ueNodes.Get(u)->GetObject<ConstantVelocityMobilityModel>();
        cv->SetPosition(Vector(cfg.distanceM, 0.5 * u, cfg.ueHeight));
        cv->SetVelocity(Vector(vms, 0.0, 0.0));
    }

    InternetStackHelper internet;
    internet.Install(remoteHostContainer);
    internet.Install(ueNodes);

    Ptr<NrHelper> nrHelper = CreateObject<NrHelper>();
    Ptr<NrPointToPointEpcHelper> epcHelper = CreateObject<NrPointToPointEpcHelper>();
    nrHelper->SetEpcHelper(epcHelper);

    Ptr<IdealBeamformingHelper> bfHelper = CreateObject<IdealBeamformingHelper>();
    nrHelper->SetBeamformingHelper(bfHelper);

    ConfigureNrHelper(nrHelper, cfg);

    CcBwpCreator ccBwpCreator;
    const uint8_t numCc = 1;
    CcBwpCreator::SimpleOperationBandConf bandConf(cfg.carrierHz, cfg.bandwidthHz, numCc);
    OperationBandInfo band = ccBwpCreator.CreateOperationBandContiguousCc(bandConf);

    std::vector<std::reference_wrapper<OperationBandInfo>> opBands;
    opBands.push_back(std::ref(band));

    ConfigureAndAssignChannels(cfg, opBands);
    BandwidthPartInfoPtrVector allBwps = CcBwpCreator::GetAllBwps(opBands);

    nrHelper->SetUePhyAttribute("NoiseFigure", DoubleValue(cfg.ueNoiseFigureDb));

    double effLossDb = ComputeEffectivePenetrationLossDb(cfg);
    nrHelper->SetGnbPhyAttribute("TxPower", DoubleValue(cfg.gnbTxPowerDbm - effLossDb));

    if (cfg.verbose)
    {
        std::cerr << "[hsr] scenario=" << ScenarioToString(cfg.scenario)
                  << " effLossDb=" << effLossDb
                  << " donor=" << cfg.donorGainDbi
                  << " service=" << cfg.serviceGainDbi
                  << " cable=" << cfg.feederCableLossDb
                  << " indoor=" << cfg.indoorDistribLossDb
                  << " coupling=" << cfg.couplingLossDb
                  << std::endl;
    }

    NetDeviceContainer gnbDevs = nrHelper->InstallGnbDevice(gnbNodes, allBwps);
    NetDeviceContainer ueDevs = nrHelper->InstallUeDevice(ueNodes, allBwps);

    Ptr<Node> pgw = epcHelper->GetPgwNode();

    PointToPointHelper p2p;
    p2p.SetDeviceAttribute("DataRate", DataRateValue(DataRate("10Gb/s")));
    p2p.SetChannelAttribute("Delay", TimeValue(MilliSeconds(1)));

    NetDeviceContainer internetDevs = p2p.Install(pgw, remoteHost);

    Ipv4AddressHelper ipv4h;
    ipv4h.SetBase("1.0.0.0", "255.0.0.0");
    ipv4h.Assign(internetDevs);

    Ipv4StaticRoutingHelper ipv4RoutingHelper;
    Ptr<Ipv4StaticRouting> remoteHostStaticRouting =
        ipv4RoutingHelper.GetStaticRouting(remoteHost->GetObject<Ipv4>());
    remoteHostStaticRouting->AddNetworkRouteTo(
        Ipv4Address("7.0.0.0"),
        Ipv4Mask("255.0.0.0"),
        1);

    Ipv4InterfaceContainer ueIfaces = epcHelper->AssignUeIpv4Address(NetDeviceContainer(ueDevs));
    for (uint32_t u = 0; u < ueNodes.GetN(); ++u)
    {
        Ptr<Ipv4StaticRouting> ueStaticRouting =
            ipv4RoutingHelper.GetStaticRouting(ueNodes.Get(u)->GetObject<Ipv4>());
        ueStaticRouting->SetDefaultRoute(epcHelper->GetUeDefaultGatewayAddress(), 1);
    }

    nrHelper->AttachToClosestGnb(ueDevs, gnbDevs);

    uint16_t basePort = 9000;
    std::vector<Ptr<UdpLatencySink>> sinks;
    std::vector<Ptr<UdpSeqTsClient>> clients;

    for (uint32_t u = 0; u < cfg.numUes; ++u)
    {
        uint16_t port = basePort + u;

        Ptr<UdpLatencySink> sink = CreateObject<UdpLatencySink>();
        sink->Setup(port);
        ueNodes.Get(u)->AddApplication(sink);
        sink->SetStartTime(Seconds(cfg.appStartS));
        sink->SetStopTime(Seconds(cfg.simTimeS));
        sinks.push_back(sink);

        InetSocketAddress dst = InetSocketAddress(ueIfaces.GetAddress(u), port);

        Time interval;
        if (cfg.saturatingLoad)
        {
            interval = MicroSeconds((uint64_t)cfg.saturatingIntervalUs);
        }
        else
        {
            double rateBps = cfg.perUeOfferedMbps * 1e6;
            double pktBits = cfg.appPktSizeBytes * 8.0;
            interval = Seconds(pktBits / rateBps);
        }

        Ptr<UdpSeqTsClient> client = CreateObject<UdpSeqTsClient>();
        client->Setup(dst, cfg.appPktSizeBytes, interval);
        remoteHost->AddApplication(client);
        client->SetStartTime(Seconds(cfg.appStartS));
        client->SetStopTime(Seconds(cfg.simTimeS));
        clients.push_back(client);
    }

    Simulator::Stop(Seconds(cfg.simTimeS));
    Simulator::Run();

    uint64_t totalRxBytes = 0;
    std::vector<double> allDelays;

    for (auto& s : sinks)
    {
        totalRxBytes += s->GetRxBytes();
        const auto& d = s->GetDelaysMs();
        allDelays.insert(allDelays.end(), d.begin(), d.end());
    }

    uint64_t totalTxPkts = 0;
    for (auto& c : clients)
    {
        totalTxPkts += c->GetTxPackets();
    }

    double effectiveTime = cfg.simTimeS - cfg.appStartS;
    if (effectiveTime <= 0.0)
    {
        effectiveTime = cfg.simTimeS;
    }

    out.throughputMbps = (totalRxBytes * 8.0) / (effectiveTime * 1e6);
    out.txPackets = totalTxPkts;
    out.rxPackets = (uint64_t)allDelays.size();
    out.pdr = (out.txPackets > 0) ? (double)out.rxPackets / (double)out.txPackets : 0.0;

    if (!allDelays.empty())
    {
        out.meanLatMs = std::accumulate(allDelays.begin(), allDelays.end(), 0.0) / allDelays.size();
        out.p50LatMs = Percentile(allDelays, 0.50);
        out.p95LatMs = Percentile(allDelays, 0.95);
    }
    else
    {
        out.meanLatMs = std::numeric_limits<double>::quiet_NaN();
        out.p50LatMs = std::numeric_limits<double>::quiet_NaN();
        out.p95LatMs = std::numeric_limits<double>::quiet_NaN();
    }

    if (cfg.numUes > 1)
    {
        std::vector<double> thr(cfg.numUes, 0.0);
        for (uint32_t u = 0; u < cfg.numUes; ++u)
        {
            thr[u] = (sinks[u]->GetRxBytes() * 8.0) / (effectiveTime * 1e6);
        }

        double sum = std::accumulate(thr.begin(), thr.end(), 0.0);
        double sumSq = 0.0;
        for (double x : thr)
        {
            sumSq += x * x;
        }
        if (sumSq > 0.0)
        {
            out.jainFairness = (sum * sum) / (thr.size() * sumSq);
        }
    }

    Simulator::Destroy();
    return out;
}

inline void RunSpeedSweep(RunConfig cfg)
{
    EnsureDir(cfg.outDir);
    std::string out = cfg.outDir + "/sweep_speed.csv";
    WriteCsvHeader(out,
                   "scenario,speed_kmph,distance_m,eff_loss_db,throughput_mbps,pdr,tx_pkts,rx_pkts,mean_lat_ms,p50_lat_ms,p95_lat_ms");

    std::vector<double> speeds = {0, 100, 200, 300, 400, 500};

    cfg.numUes = 10;
    cfg.saturatingLoad = false;
    cfg.perUeOfferedMbps = 8.19;
    cfg.distanceM = 500.0;

    for (ScenarioType s : {ScenarioType::METAL, ScenarioType::COMPOSITE, ScenarioType::REPEATER})
    {
        cfg.scenario = s;
        for (double v : speeds)
        {
            cfg.speedKmph = v;
            cfg.run++;
            double effLoss = ComputeEffectivePenetrationLossDb(cfg);
            Metrics m = RunOnce(cfg);

            std::ostringstream line;
            line << ScenarioToString(s) << "," << v << "," << cfg.distanceM << "," << effLoss << ","
                 << std::fixed << std::setprecision(6)
                 << m.throughputMbps << "," << m.pdr << "," << m.txPackets << "," << m.rxPackets
                 << "," << m.meanLatMs << "," << m.p50LatMs << "," << m.p95LatMs;
            AppendCsvLine(out, line.str());
        }
    }
}

inline void RunDistanceSweep(RunConfig cfg)
{
    EnsureDir(cfg.outDir);
    std::string out = cfg.outDir + "/sweep_distance.csv";
    WriteCsvHeader(out,
                   "scenario,speed_kmph,distance_m,eff_loss_db,throughput_mbps,pdr,tx_pkts,rx_pkts,mean_lat_ms,p50_lat_ms,p95_lat_ms");

    std::vector<double> dists = {100, 300, 500, 800, 1000, 1200, 1500};

    cfg.numUes = 10;
    cfg.saturatingLoad = false;
    cfg.perUeOfferedMbps = 8.19;
    cfg.speedKmph = 300.0;

    for (ScenarioType s : {ScenarioType::METAL, ScenarioType::COMPOSITE, ScenarioType::REPEATER})
    {
        cfg.scenario = s;
        for (double d : dists)
        {
            cfg.distanceM = d;
            cfg.run++;
            double effLoss = ComputeEffectivePenetrationLossDb(cfg);
            Metrics m = RunOnce(cfg);

            std::ostringstream line;
            line << ScenarioToString(s) << "," << cfg.speedKmph << "," << d << "," << effLoss << ","
                 << std::fixed << std::setprecision(6)
                 << m.throughputMbps << "," << m.pdr << "," << m.txPackets << "," << m.rxPackets
                 << "," << m.meanLatMs << "," << m.p50LatMs << "," << m.p95LatMs;
            AppendCsvLine(out, line.str());
        }
    }
}

inline void RunScalabilitySweep(RunConfig cfg)
{
    EnsureDir(cfg.outDir);
    std::string out = cfg.outDir + "/sweep_scalability.csv";
    WriteCsvHeader(out,
                   "num_ues,per_ue_offered_mbps,eff_loss_db,aggregate_throughput_mbps,pdr,tx_pkts,rx_pkts,mean_lat_ms,p95_lat_ms,jain_fairness");

    cfg.scenario = ScenarioType::REPEATER;
    cfg.saturatingLoad = false;
    cfg.perUeOfferedMbps = 8.19;
    cfg.speedKmph = 300.0;
    cfg.distanceM = 500.0;

    std::vector<uint32_t> users = {10, 20, 30, 40, 50};

    for (uint32_t n : users)
    {
        cfg.numUes = n;
        cfg.run++;
        double effLoss = ComputeEffectivePenetrationLossDb(cfg);
        Metrics m = RunOnce(cfg);

        std::ostringstream line;
        line << n << "," << cfg.perUeOfferedMbps << "," << effLoss << ","
             << std::fixed << std::setprecision(6)
             << m.throughputMbps << "," << m.pdr << "," << m.txPackets << "," << m.rxPackets
             << "," << m.meanLatMs << "," << m.p95LatMs << "," << m.jainFairness;
        AppendCsvLine(out, line.str());
    }
}
