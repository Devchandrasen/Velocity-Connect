#pragma once
#include <vector>
#include <algorithm>
#include <numeric>
#include <cmath>

struct Metrics
{
  double throughputMbps{0.0};
  double pdr{0.0};
  uint64_t txPackets{0};
  uint64_t rxPackets{0};

  double meanLatMs{0.0};
  double p50LatMs{0.0};
  double p95LatMs{0.0};

  double jainFairness{0.0};
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
