#pragma once
#include <sstream>
#include <iomanip>
#include <vector>
#include <functional>
#include <limits>
#include <numeric>

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
#include "hsr_handover.h"

using namespace ns3;

inline Metrics RunOnce(RunConfig cfg)
{
  ValidateRunConfig(cfg);
  Metrics out;

  RngSeedManager::SetSeed(cfg.seed);
  RngSeedManager::SetRun(cfg.run);
  ResetIpv4QueueDiscShortTransportHeaderHashEvents();

  NodeContainer gnbNodes, ueNodes, remoteHostContainer;
  gnbNodes.Create(cfg.numGnbs);
  ueNodes.Create(cfg.numUes);
  remoteHostContainer.Create(1);
  Ptr<Node> remoteHost = remoteHostContainer.Get(0);

  // Mobility
  MobilityHelper gnbMob;
  Ptr<ListPositionAllocator> gnbPositions = CreateObject<ListPositionAllocator>();
  for (uint32_t g = 0; g < cfg.numGnbs; ++g)
  {
    gnbPositions->Add(
      Vector(cfg.gnbSpacingM * g, cfg.gnbLateralOffsetM, cfg.gnbHeight));
  }
  gnbMob.SetPositionAllocator(gnbPositions);
  gnbMob.SetMobilityModel("ns3::ConstantPositionMobilityModel");
  gnbMob.Install(gnbNodes);

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

  // Internet stack
  InternetStackHelper internet;
  internet.Install(remoteHostContainer);
  internet.Install(ueNodes);

  Ipv4DropTracker ipv4DropTracker;
  for (auto nodes : {remoteHostContainer, ueNodes})
  {
    for (uint32_t index = 0; index < nodes.GetN(); ++index)
    {
      Ptr<Ipv4L3Protocol> ipv4 = nodes.Get(index)->GetObject<Ipv4L3Protocol>();
      if (!ipv4 ||
          !ipv4->TraceConnectWithoutContext(
            "Drop", MakeCallback(&Ipv4DropTracker::OnDrop, &ipv4DropTracker)))
      {
        throw std::runtime_error("Unable to connect the IPv4 drop trace source");
      }
    }
  }

  // NR + EPC
  Ptr<NrHelper> nrHelper = CreateObject<NrHelper>();
  Ptr<NrPointToPointEpcHelper> epcHelper = CreateObject<NrPointToPointEpcHelper>();
  nrHelper->SetEpcHelper(epcHelper);

  // Ideal serving-link beamforming does not create neighbour-cell beam tasks
  // and suppresses usable A3 measurements in this 5G-LENA release. Preserve it
  // for the legacy single-cell profile; corridor runs use the helper's
  // isotropic antenna defaults so neighbour RSRP remains observable.
  if (!cfg.enableHandover && cfg.passiveModel != PassiveModelType::EM_COMPLEX)
  {
    Ptr<IdealBeamformingHelper> bfHelper = CreateObject<IdealBeamformingHelper>();
    nrHelper->SetBeamformingHelper(bfHelper);
  }

  ConfigureNrHelper(nrHelper, cfg);

  // Band / BWP
  CcBwpCreator ccBwpCreator;
  const uint8_t numCc = 1;
  CcBwpCreator::SimpleOperationBandConf bandConf(cfg.carrierHz, cfg.bandwidthHz, numCc);
  OperationBandInfo band = ccBwpCreator.CreateOperationBandContiguousCc(bandConf);

  std::vector<std::reference_wrapper<OperationBandInfo>> opBands;
  opBands.emplace_back(band);

  auto emModel = ConfigureAndAssignChannels(cfg, opBands, gnbNodes, ueNodes);
  BandwidthPartInfoPtrVector allBwps = CcBwpCreator::GetAllBwps(opBands);

  // UE PHY
  nrHelper->SetUePhyAttribute("NoiseFigure", DoubleValue(cfg.ueNoiseFigureDb));

  // Apply the selected coach/passive-feedthrough system-level abstraction.
  double effLossDb = ComputeEffectivePenetrationLossDb(cfg);

  // Reciprocal equivalent-link abstraction: apply the same coach/feedthrough
  // loss to the transmitting PHY in each direction. Setting both ends avoids
  // the former downlink-only bias while each individual radio link still
  // contains the loss exactly once.
  nrHelper->SetGnbPhyAttribute("TxPower", DoubleValue(cfg.gnbTxPowerDbm - effLossDb));
  nrHelper->SetUePhyAttribute("TxPower", DoubleValue(cfg.ueTxPowerDbm - effLossDb));

  if (cfg.verbose)
  {
    std::cerr << "[hsr] scenario=" << ScenarioToString(cfg.scenario)
              << " effLossDb=" << effLossDb
              << " passiveModel=" << PassiveModelToString(cfg.passiveModel)
              << " declaredPassiveLossDb=" << cfg.declaredPassiveLossDb
              << " donor=" << cfg.donorGainDbi
              << " service=" << cfg.serviceGainDbi
              << " cable=" << cfg.feederCableLossDb
              << " indoor=" << cfg.indoorDistribLossDb
              << " coupling=" << cfg.couplingLossDb
              << " effectiveGnbTxDbm=" << (cfg.gnbTxPowerDbm - effLossDb)
              << " effectiveUeTxDbm=" << (cfg.ueTxPowerDbm - effLossDb)
              << ")\n";
  }

  NetDeviceContainer gnbDevs = nrHelper->InstallGnbDevice(gnbNodes, allBwps);
  NetDeviceContainer ueDevs  = nrHelper->InstallUeDevice(ueNodes, allBwps);

  int64_t nrAssigned = 0;
  if (cfg.nrRngStream >= 0)
  {
    nrAssigned += nrHelper->AssignStreams(gnbDevs,cfg.nrRngStream);
    nrAssigned += nrHelper->AssignStreams(ueDevs,cfg.nrRngStream+nrAssigned);
  }
  // Apply the separate channel block AFTER helper assignment (which also assigns
  // 3GPP channels). This makes the explicit override stable across device counts.
  const int64_t channelAssigned = AssignExplicitChannelStreams(cfg,allBwps);
  if (cfg.nrRngStream >= 0 && cfg.channelRngStream >= 0 &&
      cfg.nrRngStream < cfg.channelRngStream+channelAssigned &&
      cfg.channelRngStream < cfg.nrRngStream+nrAssigned)
    throw std::invalid_argument("nrRngStream and channelRngStream blocks overlap");
  if (cfg.nrRngStream >= 0 || cfg.channelRngStream >= 0)
  {
    WriteCsvHeader(cfg.outDir+"/rng_stream_audit.csv",
      "seed,run,nr_first,nr_count,channel_override_first,channel_override_count,common_channel_realizations_verified");
    AppendCsvLine(cfg.outDir+"/rng_stream_audit.csv",std::to_string(cfg.seed)+","+
      std::to_string(cfg.run)+","+std::to_string(cfg.nrRngStream)+","+std::to_string(nrAssigned)+","+
      std::to_string(cfg.channelRngStream)+","+std::to_string(channelAssigned)+",0");
  }

  // EPC: remote host <-> PGW
  Ptr<Node> pgw = epcHelper->GetPgwNode();
  PointToPointHelper p2p;
  p2p.SetDeviceAttribute("DataRate", DataRateValue(DataRate("10Gb/s")));
  p2p.SetChannelAttribute("Delay", TimeValue(MilliSeconds(1)));
  NetDeviceContainer internetDevs = p2p.Install(pgw, remoteHost);

  Ipv4AddressHelper ipv4h;
  ipv4h.SetBase("1.0.0.0", "255.0.0.0");
  Ipv4InterfaceContainer internetIfaces = ipv4h.Assign(internetDevs);
  const Ipv4Address remoteHostAddress = internetIfaces.GetAddress(1);

  Ipv4StaticRoutingHelper ipv4RoutingHelper;
  Ptr<Ipv4StaticRouting> remoteHostStaticRouting =
    ipv4RoutingHelper.GetStaticRouting(remoteHost->GetObject<Ipv4>());
  remoteHostStaticRouting->AddNetworkRouteTo(Ipv4Address("7.0.0.0"),
                                             Ipv4Mask("255.0.0.0"), 1);

  // UE IPs
  Ipv4InterfaceContainer ueIfaces = epcHelper->AssignUeIpv4Address(NetDeviceContainer(ueDevs));
  for (uint32_t u = 0; u < ueNodes.GetN(); ++u)
  {
    Ptr<Ipv4StaticRouting> ueStaticRouting =
      ipv4RoutingHelper.GetStaticRouting(ueNodes.Get(u)->GetObject<Ipv4>());
    ueStaticRouting->SetDefaultRoute(epcHelper->GetUeDefaultGatewayAddress(), 1);
  }

  HandoverTracker handoverTracker;
  std::map<uint64_t, uint32_t> imsiToUe;
  const uint16_t initialCellId =
    DynamicCast<NrGnbNetDevice>(gnbDevs.Get(0))->GetCellId();

  // Attach UEs. Corridor runs begin on cell 0 so A3 measurement reports drive
  // subsequent X2 handovers; legacy single-cell runs retain closest-cell attach.
  if (cfg.enableHandover)
  {
    for (uint32_t g = 0; g < gnbDevs.GetN(); ++g)
    {
      Ptr<NrGnbRrc> gnbRrc =
        DynamicCast<NrGnbNetDevice>(gnbDevs.Get(g))->GetRrc();
      const bool reportConnected = gnbRrc->TraceConnectWithoutContext(
        "RecvMeasurementReport",
        MakeCallback(&HandoverTracker::OnMeasurementReport, &handoverTracker));
      if (!reportConnected)
      {
        throw std::runtime_error("Unable to connect the gNB measurement-report trace source");
      }
    }

    for (uint32_t u = 0; u < ueDevs.GetN(); ++u)
    {
      nrHelper->AttachToGnb(ueDevs.Get(u), gnbDevs.Get(0));
    }
    nrHelper->AddX2Interface(gnbNodes);
  }
  else
  {
    nrHelper->AttachToClosestGnb(ueDevs, gnbDevs);
  }

  if (cfg.enableHandover)
  {
    for (uint32_t u = 0; u < ueDevs.GetN(); ++u)
    {
      Ptr<NrUeNetDevice> ueDevice = DynamicCast<NrUeNetDevice>(ueDevs.Get(u));
      imsiToUe[ueDevice->GetImsi()] = u;
      Ptr<NrUeRrc> rrc = ueDevice->GetRrc();
      const bool startConnected = rrc->TraceConnectWithoutContext(
        "HandoverStart", MakeCallback(&HandoverTracker::OnStart, &handoverTracker));
      const bool endConnected = rrc->TraceConnectWithoutContext(
        "HandoverEndOk", MakeCallback(&HandoverTracker::OnEndOk, &handoverTracker));
      const bool errorConnected = rrc->TraceConnectWithoutContext(
        "HandoverEndError", MakeCallback(&HandoverTracker::OnEndError, &handoverTracker));
      if (!startConnected || !endConnected || !errorConnected)
      {
        throw std::runtime_error("Unable to connect one or more UE handover trace sources");
      }
    }
  }

  // Apps
  uint16_t basePort = 9000;
  std::vector<Ptr<UdpLatencySink>> sinks;
  std::vector<Ptr<UdpSeqTsClient>> clients;
  const double appStopS = ResolveApplicationStopS(cfg);

  for (uint32_t u = 0; u < cfg.numUes; ++u)
  {
    uint16_t port = basePort + u;

    Ptr<UdpLatencySink> sink = CreateObject<UdpLatencySink>();
    sink->Setup(port);
    Ptr<Node> sinkNode =
      cfg.trafficDirection == TrafficDirection::DOWNLINK
        ? ueNodes.Get(u)
        : remoteHost;
    sinkNode->AddApplication(sink);
    sink->SetStartTime(Seconds(cfg.appStartS));
    sink->SetStopTime(Seconds(appStopS));
    sinks.push_back(sink);

    const Ipv4Address destinationAddress =
      cfg.trafficDirection == TrafficDirection::DOWNLINK
        ? ueIfaces.GetAddress(u)
        : remoteHostAddress;
    InetSocketAddress dst = InetSocketAddress(destinationAddress, port);

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
    Ptr<Node> clientNode =
      cfg.trafficDirection == TrafficDirection::DOWNLINK
        ? remoteHost
        : ueNodes.Get(u);
    clientNode->AddApplication(client);
    client->SetStartTime(Seconds(cfg.appStartS));
    client->SetStopTime(Seconds(appStopS));
    clients.push_back(client);
  }

  Simulator::Stop(Seconds(cfg.simTimeS));
  Simulator::Run();
  if (emModel) emModel->WriteRuntimeAudit();
  out.badIpv4LengthDrops = ipv4DropTracker.GetBadLengthDrops();
  out.shortTransportHeaderHashEvents =
    GetIpv4QueueDiscShortTransportHeaderHashEvents();

  // Aggregate stats
  uint64_t totalRxBytes = 0;
  uint64_t totalRxPackets = 0;
  std::vector<double> allDelays;

  std::vector<double> perUeThroughput;
  perUeThroughput.reserve(cfg.numUes);
  for (uint32_t u = 0; u < cfg.numUes; ++u)
  {
    auto& s = sinks.at(u);
    auto& c = clients.at(u);
    totalRxBytes += s->GetRxBytes();
    totalRxPackets += s->GetRxPackets();
    const auto& d = s->GetDelaysMs();
    const auto& receiveTimes = s->GetRxTimesNs();
    allDelays.insert(allDelays.end(), d.begin(), d.end());
    const std::size_t recordedPackets = std::min(d.size(), receiveTimes.size());
    for (std::size_t index = 0; index < recordedPackets; ++index)
    {
      PacketReception reception;
      reception.ueIndex = u;
      reception.receiveTimeS = static_cast<double>(receiveTimes[index]) / 1e9;
      reception.latencyMs = d[index];
      out.packetReceptions.push_back(reception);
    }
    const double effectiveTime = appStopS - cfg.appStartS;
    UeMetrics ue;
    ue.ueIndex = u;
    ue.txPackets = c->GetTxPackets();
    ue.rxPackets = s->GetRxPackets();
    ue.throughputMbps =
      effectiveTime > 0.0 ? (s->GetRxBytes() * 8.0) / (effectiveTime * 1e6) : 0.0;
    ue.pdr =
      ue.txPackets > 0 ? static_cast<double>(ue.rxPackets) / ue.txPackets : 0.0;
    if (!d.empty())
    {
      ue.meanLatMs = std::accumulate(d.begin(), d.end(), 0.0) / d.size();
      ue.p95LatMs = Percentile(d, 0.95);
    }
    out.ueMetrics.push_back(ue);
    perUeThroughput.push_back(ue.throughputMbps);
  }

  uint64_t totalTxPkts = 0;
  for (auto& c : clients) totalTxPkts += c->GetTxPackets();

  if (cfg.enableHandover)
  {
    for (const auto& item : imsiToUe)
    {
      handoverTracker.AddApplicationGap(item.first, sinks.at(item.second)->GetRxTimesNs());
      Ptr<NrUeNetDevice> ueDevice =
        DynamicCast<NrUeNetDevice>(ueDevs.Get(item.second));
      UeCellState cellState;
      cellState.imsi = item.first;
      cellState.initialCellId = initialCellId;
      cellState.finalCellId = ueDevice->GetRrc()->GetCellId();
      out.ueCellStates.push_back(cellState);
    }
    for (const auto& event : handoverTracker.Events())
    {
      const bool inMeasurementWindow =
        !cfg.guardedCorridor ||
        (event.startTimeS >= cfg.appStartS && event.startTimeS < appStopS);
      if (inMeasurementWindow)
      {
        out.handoverEvents.push_back(event);
      }
    }
    for (const auto& measurement : handoverTracker.Measurements())
    {
      const bool inMeasurementWindow =
        !cfg.guardedCorridor ||
        (measurement.timeS >= cfg.appStartS && measurement.timeS < appStopS);
      if (inMeasurementWindow)
      {
        out.rsrpMeasurements.push_back(measurement);
      }
    }
    out.handoverAttempts = static_cast<uint32_t>(out.handoverEvents.size());

    std::vector<double> durations;
    std::vector<double> applicationGaps;
    for (const auto& event : out.handoverEvents)
    {
      if (event.completed && event.success)
      {
        out.handoverSuccesses++;
      }
      else
      {
        out.handoverFailures++;
      }
      if (std::isfinite(event.protocolDurationMs))
      {
        durations.push_back(event.protocolDurationMs);
      }
      if (std::isfinite(event.applicationGapMs))
      {
        applicationGaps.push_back(event.applicationGapMs);
      }
    }
    if (!durations.empty())
    {
      out.meanHandoverDurationMs =
        std::accumulate(durations.begin(), durations.end(), 0.0) / durations.size();
      out.maxHandoverDurationMs = *std::max_element(durations.begin(), durations.end());
    }
    if (!applicationGaps.empty())
    {
      out.meanApplicationGapMs =
        std::accumulate(applicationGaps.begin(), applicationGaps.end(), 0.0) /
        applicationGaps.size();
      out.maxApplicationGapMs =
        *std::max_element(applicationGaps.begin(), applicationGaps.end());
    }
  }

  double effectiveTime = appStopS - cfg.appStartS;
  if (effectiveTime <= 0.0) effectiveTime = cfg.simTimeS;

  out.throughputMbps = (totalRxBytes * 8.0) / (effectiveTime * 1e6);
  out.txPackets = totalTxPkts;
  out.rxPackets = totalRxPackets;
  out.pdr = (out.txPackets > 0) ? (double)out.rxPackets / (double)out.txPackets : 0.0;
  out.p05UeThroughputMbps = Percentile(perUeThroughput, 0.05);
  out.medianUeThroughputMbps = Percentile(perUeThroughput, 0.50);

  // ✅ reviewer-safe: latency undefined when no packets received
  if (!allDelays.empty())
  {
    out.meanLatMs = std::accumulate(allDelays.begin(), allDelays.end(), 0.0) / allDelays.size();
    out.p50LatMs  = Percentile(allDelays, 0.50);
    out.p95LatMs  = Percentile(allDelays, 0.95);
  }
  else
  {
    out.meanLatMs = std::numeric_limits<double>::quiet_NaN();
    out.p50LatMs  = std::numeric_limits<double>::quiet_NaN();
    out.p95LatMs  = std::numeric_limits<double>::quiet_NaN();
  }

  // Jain fairness is exactly 1 for a single active flow.
  if (cfg.numUes == 1)
  {
    out.jainFairness = 1.0;
  }
  else if (cfg.numUes > 1)
  {
    std::vector<double> thr(cfg.numUes, 0.0);
    for (uint32_t u = 0; u < cfg.numUes; ++u)
      thr[u] = (sinks[u]->GetRxBytes() * 8.0) / (effectiveTime * 1e6);

    double sum = std::accumulate(thr.begin(), thr.end(), 0.0);
    double sumSq = 0.0;
    for (double x : thr) sumSq += x * x;
    if (sumSq > 0.0) out.jainFairness = (sum * sum) / (thr.size() * sumSq);
  }

  Simulator::Destroy();
  return out;
}

inline void RunSingle(RunConfig cfg)
{
  ValidateRunConfig(cfg);
  if (cfg.passiveModel == PassiveModelType::EM_COMPLEX)
  {
    // Preflight before creating any output, including failed/unsupported inputs.
    hsr::em::Bridge bridge(cfg.emTouchstonePath,cfg.emOperatorsPath,cfg.emMapping);
    bridge.ValidateRange(cfg.carrierHz-cfg.bandwidthHz/2,cfg.carrierHz+cfg.bandwidthHz/2);
    const hsr::em::Position gnb{0,cfg.gnbLateralOffsetM,cfg.gnbHeight};
    const hsr::em::Position ue{cfg.distanceM,0,cfg.ueHeight};
    hsr::em::Require(bridge.installation.gnb == gnb && bridge.installation.ue == ue,
                    "operator geometry must equal configured static link");
    if (std::filesystem::exists(cfg.outDir) && !std::filesystem::is_empty(cfg.outDir))
      throw std::invalid_argument("em_complex requires a fresh empty outDir; existing results are protected");
  }
  EnsureDir(cfg.outDir);
  const std::string path = cfg.outDir + "/single_run.csv";
  WriteCsvHeader(path,
    "scenario,passive_model,traffic_direction,nr_scenario,nr_condition,shadowing,"
    "speed_kmph,distance_m,gnb_height_m,gnb_lateral_offset_m,ue_height_m,"
    "num_ues,num_gnbs,gnb_spacing_m,guarded_corridor,channel_update_period_ms,"
    "sim_time_s,app_start_s,app_stop_s,enable_srs,"
    "enable_handover,use_ideal_rrc,handover_hysteresis_db,handover_ttt_ms,seed,run,"
    "declared_passive_loss_db,"
    "feeder_loss_db,coupling_loss_db,indoor_path_loss_db,donor_gain_dbi,"
    "service_gain_dbi,network_loss_db,aperture_gain_db,eff_loss_db,"
    "gnb_tx_power_dbm,ue_tx_power_dbm,effective_gnb_tx_power_dbm,"
    "effective_ue_tx_power_dbm,"
    "numerology,scs_khz,throughput_mbps,p05_ue_throughput_mbps,"
    "median_ue_throughput_mbps,pdr,tx_pkts,rx_pkts,mean_lat_ms,"
    "p50_lat_ms,p95_lat_ms,jain_fairness,handover_attempts,handover_successes,"
    "handover_failures,mean_handover_duration_ms,max_handover_duration_ms,"
    "mean_application_gap_ms,max_application_gap_ms,bad_ipv4_length_drops,"
    "short_transport_header_hash_events,channel_path,em_mapping,em_touchstone,em_operators,"
    "nr_rng_stream,channel_rng_stream,common_channel_realizations_verified");

  Metrics m = RunOnce(cfg);
  PassiveLinkBudget passiveBudget;
  const bool hasComponentBudget =
    cfg.scenario == ScenarioType::REPEATER &&
    cfg.passiveModel == PassiveModelType::COMPONENT_BUDGET;
  if (hasComponentBudget)
  {
    passiveBudget = ComputePassiveLinkBudget(cfg);
  }
  const double unavailable = std::numeric_limits<double>::quiet_NaN();
  std::ostringstream line;
  line << ScenarioToString(cfg.scenario) << ","
       << PassiveModelToString(cfg.passiveModel) << ","
       << TrafficDirectionToString(cfg.trafficDirection) << ","
       << cfg.nrScenario << ","
       << cfg.nrCondition << ","
       << (cfg.shadowingEnabled ? 1 : 0) << ","
       << cfg.speedKmph << ","
       << cfg.distanceM << ","
       << cfg.gnbHeight << ","
       << cfg.gnbLateralOffsetM << ","
       << cfg.ueHeight << ","
       << cfg.numUes << ","
       << cfg.numGnbs << ","
       << cfg.gnbSpacingM << ","
       << (cfg.guardedCorridor ? 1 : 0) << ","
       << cfg.channelUpdatePeriodMs << ","
       << cfg.simTimeS << ","
       << cfg.appStartS << ","
       << ResolveApplicationStopS(cfg) << ","
       << (cfg.enableSrs ? 1 : 0) << ","
       << (cfg.enableHandover ? 1 : 0) << ","
       << (cfg.useIdealRrc ? 1 : 0) << ","
       << cfg.handoverHysteresisDb << ","
       << cfg.handoverTimeToTriggerMs << ","
       << cfg.seed << ","
       << cfg.run << ","
       << cfg.declaredPassiveLossDb << ","
       << (hasComponentBudget ? passiveBudget.feederLossDb : unavailable) << ","
       << (hasComponentBudget ? passiveBudget.couplingLossDb : unavailable) << ","
       << (hasComponentBudget ? passiveBudget.indoorPathLossDb : unavailable) << ","
       << (hasComponentBudget ? passiveBudget.donorGainDbi : unavailable) << ","
       << (hasComponentBudget ? passiveBudget.serviceGainDbi : unavailable) << ","
       << (hasComponentBudget ? passiveBudget.networkLossDb : unavailable) << ","
       << (hasComponentBudget ? passiveBudget.apertureGainDb : unavailable) << ","
       << (cfg.passiveModel == PassiveModelType::EM_COMPLEX ? unavailable : ComputeEffectivePenetrationLossDb(cfg)) << ","
       << cfg.gnbTxPowerDbm << ","
       << cfg.ueTxPowerDbm << ","
       << (cfg.gnbTxPowerDbm - ComputeEffectivePenetrationLossDb(cfg)) << ","
       << (cfg.ueTxPowerDbm - ComputeEffectivePenetrationLossDb(cfg)) << ","
       << cfg.numerology << ","
       << ComputeSubcarrierSpacingKHz(cfg.numerology) << ","
       << std::fixed << std::setprecision(9)
       << m.throughputMbps << ","
       << m.p05UeThroughputMbps << ","
       << m.medianUeThroughputMbps << ","
       << m.pdr << ","
       << m.txPackets << ","
       << m.rxPackets << ","
       << m.meanLatMs << ","
       << m.p50LatMs << ","
       << m.p95LatMs << ","
       << m.jainFairness << ","
       << m.handoverAttempts << ","
       << m.handoverSuccesses << ","
       << m.handoverFailures << ","
       << m.meanHandoverDurationMs << ","
       << m.maxHandoverDurationMs << ","
       << m.meanApplicationGapMs << ","
       << m.maxApplicationGapMs << ","
       << m.badIpv4LengthDrops << ","
       << m.shortTransportHeaderHashEvents << ","
       << (cfg.passiveModel == PassiveModelType::EM_COMPLEX ? "em_absolute_static_siso" : "nr_legacy_scalar") << ","
       << CsvCell(cfg.passiveModel == PassiveModelType::EM_COMPLEX ? cfg.emMapping : "") << ","
       << CsvCell(cfg.emTouchstonePath) << "," << CsvCell(cfg.emOperatorsPath) << ","
       << cfg.nrRngStream << "," << cfg.channelRngStream << ",0";
  AppendCsvLine(path, line.str());

  const std::string ueMetricsPath = cfg.outDir + "/ue_metrics.csv";
  WriteCsvHeader(
    ueMetricsPath,
    "ue_index,traffic_direction,tx_pkts,rx_pkts,throughput_mbps,pdr,"
    "mean_lat_ms,p95_lat_ms");
  for (const auto& ue : m.ueMetrics)
  {
    std::ostringstream ueLine;
    ueLine << ue.ueIndex << ","
           << TrafficDirectionToString(cfg.trafficDirection) << ","
           << ue.txPackets << ","
           << ue.rxPackets << ","
           << std::fixed << std::setprecision(9)
           << ue.throughputMbps << ","
           << ue.pdr << ","
           << ue.meanLatMs << ","
           << ue.p95LatMs;
    AppendCsvLine(ueMetricsPath, ueLine.str());
  }

  const std::string packetReceptionPath = cfg.outDir + "/packet_receptions.csv";
  WriteCsvHeader(
    packetReceptionPath,
    "ue_index,traffic_direction,receive_time_s,latency_ms");
  for (const auto& reception : m.packetReceptions)
  {
    std::ostringstream receptionLine;
    receptionLine << reception.ueIndex << ","
                  << TrafficDirectionToString(cfg.trafficDirection) << ","
                  << std::fixed << std::setprecision(9)
                  << reception.receiveTimeS << ","
                  << reception.latencyMs;
    AppendCsvLine(packetReceptionPath, receptionLine.str());
  }

  const std::string eventPath = cfg.outDir + "/handover_events.csv";
  WriteCsvHeader(
    eventPath,
    "imsi,source_cell_id,target_cell_id,final_cell_id,start_time_s,end_time_s,"
    "protocol_duration_ms,application_gap_ms,success,completed");
  for (const auto& event : m.handoverEvents)
  {
    std::ostringstream eventLine;
    eventLine << event.imsi << ","
              << event.sourceCellId << ","
              << event.targetCellId << ","
              << event.finalCellId << ","
              << std::fixed << std::setprecision(9)
              << event.startTimeS << ","
              << event.endTimeS << ","
              << event.protocolDurationMs << ","
              << event.applicationGapMs << ","
              << (event.success ? 1 : 0) << ","
              << (event.completed ? 1 : 0);
    AppendCsvLine(eventPath, eventLine.str());
  }

  const std::string servingCellPath = cfg.outDir + "/ue_serving_cells.csv";
  WriteCsvHeader(servingCellPath, "imsi,initial_cell_id,final_cell_id,changed");
  for (const auto& state : m.ueCellStates)
  {
    std::ostringstream stateLine;
    stateLine << state.imsi << ","
              << state.initialCellId << ","
              << state.finalCellId << ","
              << (state.initialCellId != state.finalCellId ? 1 : 0);
    AppendCsvLine(servingCellPath, stateLine.str());
  }

  const std::string measurementPath = cfg.outDir + "/rsrp_measurements.csv";
  WriteCsvHeader(
    measurementPath,
    "time_s,imsi,serving_cell_id,serving_rsrp_code,serving_rsrp_dbm,"
    "neighbour_cell_id,neighbour_rsrp_code,neighbour_rsrp_dbm,has_neighbour");
  for (const auto& sample : m.rsrpMeasurements)
  {
    std::ostringstream sampleLine;
    sampleLine << std::fixed << std::setprecision(9)
               << sample.timeS << ","
               << sample.imsi << ","
               << sample.servingCellId << ","
               << static_cast<uint32_t>(sample.servingRsrpCode) << ","
               << sample.servingRsrpDbm << ","
               << sample.neighbourCellId << ","
               << static_cast<uint32_t>(sample.neighbourRsrpCode) << ","
               << sample.neighbourRsrpDbm << ","
               << (sample.hasNeighbour ? 1 : 0);
    AppendCsvLine(measurementPath, sampleLine.str());
  }
}

inline void RunSpeedSweep(RunConfig cfg)
{
  EnsureDir(cfg.outDir);
  std::string out = cfg.outDir + "/sweep_speed.csv";
  WriteCsvHeader(out,
    "scenario,speed_kmph,distance_m,num_ues,seed,run,eff_loss_db,numerology,scs_khz,throughput_mbps,pdr,tx_pkts,rx_pkts,mean_lat_ms,p50_lat_ms,p95_lat_ms");

  std::vector<double> speeds = {0, 100, 200, 300, 400, 500};
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
      line << ScenarioToString(s) << ","
           << v << ","
           << cfg.distanceM << ","
           << cfg.numUes << ","
           << cfg.seed << ","
           << cfg.run << ","
           << effLoss << ","
           << cfg.numerology << ","
           << ComputeSubcarrierSpacingKHz(cfg.numerology) << ","
           << std::fixed << std::setprecision(6)
           << m.throughputMbps << ","
           << m.pdr << ","
           << m.txPackets << ","
           << m.rxPackets << ","
           << m.meanLatMs << ","
           << m.p50LatMs << ","
           << m.p95LatMs;

      AppendCsvLine(out, line.str());
    }
  }
}

inline void RunDistanceSweep(RunConfig cfg)
{
  EnsureDir(cfg.outDir);
  std::string out = cfg.outDir + "/sweep_distance.csv";
  WriteCsvHeader(out,
    "scenario,speed_kmph,distance_m,num_ues,seed,run,eff_loss_db,numerology,scs_khz,throughput_mbps,pdr,tx_pkts,rx_pkts,mean_lat_ms,p50_lat_ms,p95_lat_ms");

  std::vector<double> dists = {100, 300, 500, 800, 1000, 1200, 1500};

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
      line << ScenarioToString(s) << ","
           << cfg.speedKmph << ","
           << d << ","
           << cfg.numUes << ","
           << cfg.seed << ","
           << cfg.run << ","
           << effLoss << ","
           << cfg.numerology << ","
           << ComputeSubcarrierSpacingKHz(cfg.numerology) << ","
           << std::fixed << std::setprecision(6)
           << m.throughputMbps << ","
           << m.pdr << ","
           << m.txPackets << ","
           << m.rxPackets << ","
           << m.meanLatMs << ","
           << m.p50LatMs << ","
           << m.p95LatMs;

      AppendCsvLine(out, line.str());
    }
  }
}

inline void RunScalabilitySweep(RunConfig cfg)
{
  EnsureDir(cfg.outDir);
  std::string out = cfg.outDir + "/sweep_scalability.csv";
  WriteCsvHeader(out,
    "num_ues,per_ue_offered_mbps,eff_loss_db,numerology,scs_khz,aggregate_throughput_mbps,pdr,tx_pkts,rx_pkts,mean_lat_ms,p95_lat_ms,jain_fairness");

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
    line << n << ","
         << cfg.perUeOfferedMbps << ","
         << effLoss << ","
         << cfg.numerology << ","
         << ComputeSubcarrierSpacingKHz(cfg.numerology) << ","
         << std::fixed << std::setprecision(6)
         << m.throughputMbps << ","
         << m.pdr << ","
         << m.txPackets << ","
         << m.rxPackets << ","
         << m.meanLatMs << ","
         << m.p95LatMs << ","
         << m.jainFairness;

    AppendCsvLine(out, line.str());
  }
}
