#pragma once
#include <vector>
#include <algorithm>
#include <numeric>
#include <cmath>
#include <limits>

#include "hsr_handover.h"

struct UeCellState
{
  uint64_t imsi{0};
  uint16_t initialCellId{0};
  uint16_t finalCellId{0};
};

struct UeMetrics
{
  uint32_t ueIndex{0};
  uint64_t txPackets{0};
  uint64_t rxPackets{0};
  double throughputMbps{0.0};
  double pdr{0.0};
  double meanLatMs{std::numeric_limits<double>::quiet_NaN()};
  double p95LatMs{std::numeric_limits<double>::quiet_NaN()};
};

struct PacketReception
{
  uint32_t ueIndex{0};
  double receiveTimeS{0.0};
  double latencyMs{std::numeric_limits<double>::quiet_NaN()};
};

struct Metrics
{
  double throughputMbps{0.0};
  double pdr{0.0};
  uint64_t txPackets{0};
  uint64_t rxPackets{0};

  double meanLatMs{0.0};
  double p50LatMs{0.0};
  double p95LatMs{0.0};
  double p05UeThroughputMbps{0.0};
  double medianUeThroughputMbps{0.0};

  double jainFairness{0.0};

  uint32_t handoverAttempts{0};
  uint32_t handoverSuccesses{0};
  uint32_t handoverFailures{0};
  double meanHandoverDurationMs{0.0};
  double maxHandoverDurationMs{0.0};
  double meanApplicationGapMs{0.0};
  double maxApplicationGapMs{0.0};
  uint64_t badIpv4LengthDrops{0};
  uint64_t shortTransportHeaderHashEvents{0};
  std::vector<HandoverEvent> handoverEvents;
  std::vector<RsrpMeasurement> rsrpMeasurements;
  std::vector<UeCellState> ueCellStates;
  std::vector<UeMetrics> ueMetrics;
  std::vector<PacketReception> packetReceptions;
};

class Ipv4DropTracker
{
public:
  void OnDrop(const Ipv4Header&,
              Ptr<const Packet>,
              Ipv4L3Protocol::DropReason reason,
              Ptr<Ipv4>,
              uint32_t)
  {
    if (reason == Ipv4L3Protocol::DROP_BAD_LENGTH)
    {
      ++m_badLengthDrops;
    }
  }

  uint64_t GetBadLengthDrops() const
  {
    return m_badLengthDrops;
  }

private:
  uint64_t m_badLengthDrops{0};
};

inline double Percentile(std::vector<double> v, double p)
{
  if (v.empty()) return 0.0;
  std::sort(v.begin(), v.end());
  double idx = p * (v.size() - 1);
  size_t lo = (size_t)std::floor(idx);
  size_t hi = (size_t)std::ceil(idx);
  if (hi >= v.size()) hi = v.size() - 1;
  double frac = idx - lo;
  return v[lo] * (1.0 - frac) + v[hi] * frac;
}
