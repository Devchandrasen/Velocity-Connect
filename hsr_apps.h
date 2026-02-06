#pragma once
#include <vector>
#include <cstdint>

#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/internet-module.h"
#include "ns3/applications-module.h"

using namespace ns3;

// seq(uint32) + ts(ns uint64) = 12 bytes
class SeqTsNanoHeader : public Header
{
public:
  static TypeId GetTypeId()
  {
    static TypeId tid = TypeId("ns3::SeqTsNanoHeader")
      .SetParent<Header>()
      .AddConstructor<SeqTsNanoHeader>();
    return tid;
  }
  TypeId GetInstanceTypeId() const override { return GetTypeId(); }

  void SetSeq(uint32_t s) { m_seq = s; }
  uint32_t GetSeq() const { return m_seq; }

  void SetTsNs(uint64_t t) { m_tsNs = t; }
  uint64_t GetTsNs() const { return m_tsNs; }

  uint32_t GetSerializedSize() const override { return 12; }

  void Serialize(Buffer::Iterator i) const override
  {
    i.WriteHtonU32(m_seq);
    i.WriteHtonU64(m_tsNs);
  }

  uint32_t Deserialize(Buffer::Iterator i) override
  {
    m_seq = i.ReadNtohU32();
    m_tsNs = i.ReadNtohU64();
    return GetSerializedSize();
  }

  void Print(std::ostream& os) const override
  {
    os << "seq=" << m_seq << " tsNs=" << m_tsNs;
  }

private:
  uint32_t m_seq{0};
  uint64_t m_tsNs{0};
};

class UdpSeqTsClient : public Application
{
public:
  void Setup(Address peer, uint32_t pktSizeBytes, Time interval)
  {
    m_peer = peer;
    m_pktSizeBytes = pktSizeBytes;
    m_interval = interval;
  }

  uint64_t GetTxPackets() const { return m_txPackets; }

private:
  void StartApplication() override
  {
    if (!m_socket)
    {
      m_socket = Socket::CreateSocket(GetNode(), UdpSocketFactory::GetTypeId());
      m_socket->Connect(m_peer);
    }
    m_running = true;
    m_seq = 0;
    ScheduleNext();
  }

  void StopApplication() override
  {
    m_running = false;
    if (m_sendEvent.IsPending()) Simulator::Cancel(m_sendEvent);
    if (m_socket)
    {
      m_socket->Close();
      m_socket = nullptr;
    }
  }

  void ScheduleNext()
  {
    if (!m_running) return;
    m_sendEvent = Simulator::Schedule(m_interval, &UdpSeqTsClient::SendPacket, this);
  }

  void SendPacket()
  {
    if (!m_running) return;

    SeqTsNanoHeader h;
    h.SetSeq(m_seq++);
    h.SetTsNs((uint64_t)Simulator::Now().GetNanoSeconds());

    uint32_t hdr = h.GetSerializedSize();
    uint32_t payload = (m_pktSizeBytes > hdr) ? (m_pktSizeBytes - hdr) : 0;

    Ptr<Packet> p = Create<Packet>(payload);
    p->AddHeader(h);

    m_socket->Send(p);
    m_txPackets++;

    ScheduleNext();
  }

  Ptr<Socket> m_socket;
  Address m_peer;
  bool m_running{false};
  EventId m_sendEvent;

  uint32_t m_pktSizeBytes{1024};
  Time m_interval{MilliSeconds(1)};
  uint32_t m_seq{0};
  uint64_t m_txPackets{0};
};

class UdpLatencySink : public Application
{
public:
  void Setup(uint16_t port) { m_port = port; }

  uint64_t GetRxPackets() const { return m_rxPackets; }
  uint64_t GetRxBytes() const { return m_rxBytes; }
  const std::vector<double>& GetDelaysMs() const { return m_delaysMs; }

private:
  void StartApplication() override
  {
    if (!m_socket)
    {
      m_socket = Socket::CreateSocket(GetNode(), UdpSocketFactory::GetTypeId());
      m_socket->Bind(InetSocketAddress(Ipv4Address::GetAny(), m_port));
      m_socket->SetRecvCallback(MakeCallback(&UdpLatencySink::HandleRead, this));
    }
  }

  void StopApplication() override
  {
    if (m_socket)
    {
      m_socket->Close();
      m_socket = nullptr;
    }
  }

  void HandleRead(Ptr<Socket> sock)
  {
    Address from;
    Ptr<Packet> p;
    while ((p = sock->RecvFrom(from)))
    {
      m_rxPackets++;
      m_rxBytes += p->GetSize();

      SeqTsNanoHeader h;
      if (p->GetSize() >= h.GetSerializedSize())
      {
        p->RemoveHeader(h);
        uint64_t txNs = h.GetTsNs();
        uint64_t nowNs = (uint64_t)Simulator::Now().GetNanoSeconds();
        m_delaysMs.push_back((double)(nowNs - txNs) / 1e6);
      }
    }
  }

  Ptr<Socket> m_socket;
  uint16_t m_port{0};
  uint64_t m_rxPackets{0};
  uint64_t m_rxBytes{0};
  std::vector<double> m_delaysMs;
};
