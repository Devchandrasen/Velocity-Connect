#include "hsr_nr.h"
#include "ns3/constant-position-mobility-model.h"
#include "ns3/spectrum-model.h"
#include <iostream>

using namespace ns3;
int main(int argc,char** argv)
{
  try
  {
    hsr::em::Require(argc == 3,"usage: test_em_channel_ns3 fixture operators");
    auto bridge = std::make_shared<hsr::em::Bridge>(argv[1],argv[2],"cross");
    auto gnb=CreateObject<ConstantPositionMobilityModel>();
    auto ue=CreateObject<ConstantPositionMobilityModel>();
    auto unknown=CreateObject<ConstantPositionMobilityModel>();
    gnb->SetPosition(Vector(0,0,10)); ue->SetPosition(Vector(500,0,1.5));
    auto loss=CreateObject<HsrEmSpectrumLossModel>();
    loss->Setup(bridge,gnb,ue,"");
    Bands bands{{3.45e9,3.46e9,3.47e9},{3.53e9,3.54e9,3.55e9}};
    auto spectrum=Create<SpectrumModel>(bands);
    auto params=Create<SpectrumSignalParameters>();
    params->psd=Create<SpectrumValue>(spectrum);
    (*params->psd)[0]=2e-9; (*params->psd)[1]=7e-9;
    auto dl=loss->CalcRxPowerSpectralDensity(params,gnb,ue);
    auto ul=loss->CalcRxPowerSpectralDensity(params,ue,gnb);
    auto same=loss->CalcRxPowerSpectralDensity(params,ue,ue);
    for (size_t i=0;i<2;++i)
    {
      hsr::em::Require(std::abs((*dl)[i]/(*params->psd)[i]-bridge->Gain(bands[i].fc)) < 1e-20,"per-band received PSD mismatch");
      hsr::em::Require(std::abs((*dl)[i]-(*ul)[i]) < 1e-30,"reciprocity mismatch");
      hsr::em::Require((*same)[i]==(*params->psd)[i],"same-role link was attenuated");
    }
    hsr::em::Require((*params->psd)[0]==2e-9 && (*params->psd)[1]==7e-9,"input PSD mutated");
    bool rejected=false;
    try { loss->CalcRxPowerSpectralDensity(params,gnb,unknown); }
    catch(const std::invalid_argument&) { rejected=true; }
    hsr::em::Require(rejected,"unknown role accepted without operators");
    ue->SetPosition(Vector(501,0,1.5)); rejected=false;
    try { loss->CalcRxPowerSpectralDensity(params,gnb,ue); }
    catch(const std::invalid_argument&) { rejected=true; }
    hsr::em::Require(rejected,"geometry mismatch accepted");
    Simulator::Destroy();
    std::cout << "PASS pinned ns-3 per-band PSD, reciprocity, role filtering, immutable input, geometry guard\n";
  }
  catch(const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
