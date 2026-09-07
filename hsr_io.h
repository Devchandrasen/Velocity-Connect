#pragma once
#include <string>
#include <fstream>
#include <filesystem>
#include <stdexcept>
#include <iomanip>
#include "hsr_types.h"
#include "hsr_em_channel.h"

inline void EnsureDir(const std::string& dir)
{
  if (dir.empty()) return;

  std::error_code ec;
  std::filesystem::create_directories(dir, ec);
  if (ec)
  {
    throw std::runtime_error("Unable to create output directory '" + dir + "': " + ec.message());
  }
}

inline std::string CsvCell(const std::string& value)
{
  std::string s = "\"";
  for (char c : value) { if (c == '"') s += '"'; s += c; }
  return s+'"';
}

inline void WriteCsvHeader(const std::string& path, const std::string& header)
{
  std::ofstream f(path, std::ios::out);
  if (!f)
  {
    throw std::runtime_error("Unable to open CSV for writing: " + path);
  }
  f << header << "\n";
}

inline void AppendCsvLine(const std::string& path, const std::string& line)
{
  std::ofstream f(path, std::ios::out | std::ios::app);
  if (!f)
  {
    throw std::runtime_error("Unable to open CSV for appending: " + path);
  }
  f << line << "\n";
}

inline void WriteEmBridgeAudit(const RunConfig& cfg, const hsr::em::Bridge& bridge)
{
  // RunSingle requires an empty EM output directory. Preserve exact input bytes,
  // including provenance, complex phase, projection and absolute geometry.
  for (const auto& item : {
      std::make_pair("em_bridge_input.s4p", &bridge.fixture.raw),
      std::make_pair("em_bridge_operators.csv", &bridge.installation.raw)})
  {
    std::ofstream f(cfg.outDir+"/"+item.first, std::ios::binary);
    if (!f || !(f << *item.second)) throw std::runtime_error("Unable to snapshot EM inputs");
  }
  std::ofstream f(cfg.outDir+"/em_bridge_audit.md");
  if (!f) throw std::runtime_error("Unable to write EM audit");
  f << "# EM bridge runtime configuration\n\n"
    << "Evidence: " << bridge.installation.metadata.at("evidence") << "\n\n"
    << "Provenance: " << bridge.installation.metadata.at("provenance") << "\n\n"
    << "Fixture source: " << cfg.emTouchstonePath << "\n\n"
    << "Operators source: " << cfg.emOperatorsPath << "\n\n"
    << "Mapping: " << cfg.emMapping << " (straight = service-terminal permutation of cross fixture)\n\n"
    << "H(f) = D(f) + C_service(f) T(f) C_donor(f); gain = |q^H H p|^2.\n\n"
    << "Absolute static installed power-wave operators. NR pathloss/fading/beamforming and scalar Tx attenuation are disabled.\n\n"
    << "Single stream, fixed explicit Jones projections, SISO feedback. No spatial multiplexing, embedded patterns, or installation calibration is inferred.\n\n"
    << "Reciprocity: H_UL = H_DL^T; p_UL=conj(q_DL), q_UL=conj(p_DL). Matched 50-ohm HFSS terminals only; no multiple-reflection loading solve.\n\n"
    << "Per-band Cartesian interpolation at RB centre; no extrapolation. Band-edge coverage is checked. Phase delay is not a packet time-domain impulse response.\n\n"
    << "seed=" << cfg.seed << ", run=" << cfg.run << ", nr_rng_stream=" << cfg.nrRngStream
    << "; channel RNG absent. Matching RNG identifiers is not verified common realizations.\n\n"
    << "Exact inputs: em_bridge_input.s4p, em_bridge_operators.csv. Runtime PSD evidence: em_bridge_bands.csv and em_bridge_runtime.csv.\n";
  if (!f) throw std::runtime_error("Failed writing EM audit");
}
