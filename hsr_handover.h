#pragma once

#include <algorithm>
#include <cstdint>
#include <limits>
#include <map>
#include <numeric>
#include <vector>

#include "ns3/core-module.h"
#include "ns3/nr-module.h"

using namespace ns3;

struct HandoverEvent
{
  uint64_t imsi{0};
  uint16_t sourceCellId{0};
  uint16_t targetCellId{0};
  uint16_t finalCellId{0};
  double startTimeS{0.0};
  double endTimeS{std::numeric_limits<double>::quiet_NaN()};
  double protocolDurationMs{std::numeric_limits<double>::quiet_NaN()};
  double applicationGapMs{std::numeric_limits<double>::quiet_NaN()};
  bool success{false};
  bool completed{false};
};

struct RsrpMeasurement
{
  uint64_t imsi{0};
  uint16_t servingCellId{0};
  uint16_t neighbourCellId{0};
  uint8_t servingRsrpCode{0};
  uint8_t neighbourRsrpCode{0};
  double servingRsrpDbm{std::numeric_limits<double>::quiet_NaN()};
  double neighbourRsrpDbm{std::numeric_limits<double>::quiet_NaN()};
  bool hasNeighbour{false};
  double timeS{0.0};
};

class HandoverTracker
{
public:
  void OnStart(uint64_t imsi, uint16_t sourceCellId, uint16_t, uint16_t targetCellId)
  {
    HandoverEvent event;
    event.imsi = imsi;
    event.sourceCellId = sourceCellId;
    event.targetCellId = targetCellId;
    event.startTimeS = Simulator::Now().GetSeconds();
    m_events.push_back(event);
    m_active[imsi] = m_events.size() - 1;
  }

  void OnEndOk(uint64_t imsi, uint16_t cellId, uint16_t)
  {
    Finish(imsi, cellId, true);
  }

  void OnEndError(uint64_t imsi, uint16_t cellId, uint16_t)
  {
    Finish(imsi, cellId, false);
  }

  void AddApplicationGap(uint64_t imsi, const std::vector<uint64_t>& rxTimesNs)
  {
    for (auto& event : m_events)
    {
      if (event.imsi != imsi || !event.completed || rxTimesNs.empty())
      {
        continue;
      }

      const uint64_t startNs = static_cast<uint64_t>(event.startTimeS * 1e9);
      const uint64_t endNs = static_cast<uint64_t>(event.endTimeS * 1e9);
      auto before = std::lower_bound(rxTimesNs.begin(), rxTimesNs.end(), startNs);
      auto after = std::lower_bound(rxTimesNs.begin(), rxTimesNs.end(), endNs);
      if (before != rxTimesNs.begin() && after != rxTimesNs.end())
      {
        --before;
        event.applicationGapMs =
          static_cast<double>(*after - *before) / 1e6;
      }
    }
  }

  const std::vector<HandoverEvent>& Events() const
  {
    return m_events;
  }

  void OnMeasurementReport(
    uint64_t imsi,
    uint16_t servingCellId,
    uint16_t,
    NrRrcSap::MeasurementReport report)
  {
    const auto& results = report.measResults;
    if (results.haveMeasResultNeighCells && !results.measResultListEutra.empty())
    {
      for (const auto& neighbour : results.measResultListEutra)
      {
        RsrpMeasurement sample;
        sample.imsi = imsi;
        sample.servingCellId = servingCellId;
        sample.neighbourCellId = neighbour.physCellId;
        sample.servingRsrpCode = results.measResultPCell.rsrpResult;
        sample.servingRsrpDbm = nr::EutranMeasurementMapping::RsrpRange2Dbm(
          sample.servingRsrpCode);
        sample.neighbourRsrpCode =
          neighbour.haveRsrpResult ? neighbour.rsrpResult : 0;
        sample.hasNeighbour = neighbour.haveRsrpResult;
        if (sample.hasNeighbour)
        {
          sample.neighbourRsrpDbm = nr::EutranMeasurementMapping::RsrpRange2Dbm(
            sample.neighbourRsrpCode);
        }
        sample.timeS = Simulator::Now().GetSeconds();
        m_measurements.push_back(sample);
      }
    }
    else
    {
      RsrpMeasurement sample;
      sample.imsi = imsi;
      sample.servingCellId = servingCellId;
      sample.servingRsrpCode = results.measResultPCell.rsrpResult;
      sample.servingRsrpDbm = nr::EutranMeasurementMapping::RsrpRange2Dbm(
        sample.servingRsrpCode);
      sample.timeS = Simulator::Now().GetSeconds();
      m_measurements.push_back(sample);
    }
  }

  const std::vector<RsrpMeasurement>& Measurements() const
  {
    return m_measurements;
  }

private:
  void Finish(uint64_t imsi, uint16_t cellId, bool success)
  {
    auto active = m_active.find(imsi);
    if (active == m_active.end())
    {
      return;
    }
    HandoverEvent& event = m_events.at(active->second);
    event.finalCellId = cellId;
    event.endTimeS = Simulator::Now().GetSeconds();
    event.protocolDurationMs = (event.endTimeS - event.startTimeS) * 1000.0;
    event.success = success;
    event.completed = true;
    m_active.erase(active);
  }

  std::vector<HandoverEvent> m_events;
  std::vector<RsrpMeasurement> m_measurements;
  std::map<uint64_t, std::size_t> m_active;
};
