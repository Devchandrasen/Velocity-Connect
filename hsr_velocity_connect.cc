#include "ns3/core-module.h"
#include "hsr/hsr_runner.h"
#include "hsr/hsr_types.h"
#include "hsr/hsr_io.h"

using namespace ns3;

int main(int argc, char* argv[])
{
  RunConfig cfg;

  bool doSpeed = true;
  bool doDistance = true;
  bool doScalability = true;

  CommandLine cmd;
  cmd.AddValue("outDir", "Output directory", cfg.outDir);
  cmd.AddValue("simTime", "Simulation time (s)", cfg.simTimeS);
  cmd.AddValue("appStart", "Application start time (s)", cfg.appStartS);

  cmd.AddValue("seed", "RNG seed", cfg.seed);
  cmd.AddValue("run", "RNG run base", cfg.run);

  cmd.AddValue("distance", "Distance (m) used for speed sweep", cfg.distanceM);
  cmd.AddValue("speed", "Speed (km/h) used for distance sweep", cfg.speedKmph);

  cmd.AddValue("nrScenario", "NR scenario string (UMi/RMa/UMa/etc.)", cfg.nrScenario);
  cmd.AddValue("nrCondition", "NR condition (LOS/NLOS/Default)", cfg.nrCondition);
  cmd.AddValue("nrChannelModel", "NR channel model (ThreeGpp/TwoRay/NYU)", cfg.nrChannelModel);
  cmd.AddValue("shadowing", "Enable shadowing (0/1)", cfg.shadowingEnabled);
  cmd.AddValue("scheduler", "Scheduler TypeId string", cfg.schedulerType);

  // ✅ Scalability crash fix: SRS disabled by default for DL-focused study
  cmd.AddValue("enableSrs", "Enable SRS scheduling (0/1). Default 0.", cfg.enableSrs);

  cmd.AddValue("gnbTxPowerDbm", "gNB Tx power (dBm)", cfg.gnbTxPowerDbm);
  cmd.AddValue("ueNoiseFigureDb", "UE noise figure (dB)", cfg.ueNoiseFigureDb);

  cmd.AddValue("saturatingLoad", "Use saturating traffic (0/1)", cfg.saturatingLoad);
  cmd.AddValue("perUeOfferedMbps", "Per-UE offered load (Mbps) if not saturating", cfg.perUeOfferedMbps);
  cmd.AddValue("saturatingIntervalUs", "Saturating inter-packet interval (us)", cfg.saturatingIntervalUs);

  cmd.AddValue("verbose", "Print effective-loss breakdown (0/1)", cfg.verbose);

  // Baseline VPL
  cmd.AddValue("metalVplDb", "Metal coach VPL (dB)", cfg.metalVplDb);
  cmd.AddValue("compositeVplDb", "Composite coach VPL (dB)", cfg.compositeVplDb);

  // Velocity Connect link budget terms (your novel modelling idea)
  cmd.AddValue("donorGainDbi", "Donor antenna gain (dBi)", cfg.donorGainDbi);
  cmd.AddValue("serviceGainDbi", "Service antenna gain (dBi)", cfg.serviceGainDbi);
  cmd.AddValue("feederCableLossDb", "Feeder coax loss (dB)", cfg.feederCableLossDb);
  cmd.AddValue("indoorDistribLossDb", "Indoor distribution loss (dB)", cfg.indoorDistribLossDb);
  cmd.AddValue("couplingLossDb", "Coupler/mismatch/connector loss (dB)", cfg.couplingLossDb);

  cmd.AddValue("doSpeed", "Run speed sweep", doSpeed);
  cmd.AddValue("doDistance", "Run distance sweep", doDistance);
  cmd.AddValue("doScalability", "Run scalability sweep", doScalability);

  cmd.Parse(argc, argv);

  EnsureDir(cfg.outDir);

  if (doSpeed) RunSpeedSweep(cfg);
  if (doDistance) RunDistanceSweep(cfg);
  if (doScalability) RunScalabilitySweep(cfg);

  std::cerr << "Done. CSVs saved in: " << cfg.outDir << std::endl;
  return 0;
}
