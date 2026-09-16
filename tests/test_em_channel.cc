#include "hsr_em_channel.h"
#include "hsr_types.h"
#include <filesystem>
#include <iomanip>
#include <iostream>

using namespace hsr::em;
int checks = 0;
void Check(bool ok, const char* message)
{
  ++checks;
  if (!ok) throw std::runtime_error(message);
}
template<class Fn> void Reject(Fn fn)
{
  bool rejected = false;
  try { fn(); } catch (const std::exception&) { rejected = true; }
  Check(rejected,"required rejection did not occur");
}
bool Near(Complex a, Complex b, double eps=1e-12) { return std::abs(a-b) <= eps; }
Matrix2 Scale(Matrix2 h, Complex z) { for (auto& v:h) v*=z; return h; }
const Matrix2 I{1,0,0,1};

std::string SyntheticOperators()
{
  std::ostringstream o;
  o << "# schema=hsr-em-operators-v1\n"
    << "# provenance=tests/test_em_channel.cc:SyntheticOperators; arbitrary normalized test operators, NOT installed measurements\n"
    << "# evidence=synthetic\n# normalization=absolute_power_waves_50ohm\n"
    << "# basis=donor/service terminal order as fixture; abstract orthonormal two-mode radio bases\n"
    << "# gnb_position_m=0,0,10\n# ue_position_m=500,0,1.5\n"
    << "# tx_projection=1,0,0,0\n# rx_projection=0.6,0,0.8,0\n"
    << OperatorHeader() << '\n';
  o << std::setprecision(17);
  for (double f : {3.3e9,3.7e9})
  {
    o << f;
    for (const auto& m : {Scale(I,1e-5),Scale(I,.01),Scale(I,.01)})
      for (const auto& z:m) o << ',' << z.real() << ',' << z.imag();
    o << '\n';
  }
  return o.str();
}
int main(int argc,char** argv)
{
  try
  {
    Require(argc == 3,"usage: test_em_channel repo scratch");
    const std::string root = argv[1], scratch = argv[2];
    std::filesystem::create_directories(scratch);
    const auto opPath = scratch+"/synthetic_operators.csv";
    std::ofstream(opPath) << SyntheticOperators();
    const auto v4Path = root+"/fixtures/hfss/PTF_V4_Balanced_Cross.s4p";
    const auto v5Path = root+"/fixtures/hfss/PTF_V5_Delay25ps_Cross.s4p";
    Bridge v4(v4Path,opPath,"cross"), v5(v5Path,opPath,"cross");
    Check(v4.fixture.samples.size() == 21,"V4 fixture grid");
    Check(v5.fixture.samples.size() == 21,"V5 fixture grid");
    for (const auto* b : {&v4,&v5})
    {
      b->ValidateRange(3.45e9,3.55e9);
      const auto& s = b->fixture.samples.front().s;
      const auto t = b->fixture.Transfer(3.3e9,"cross");
      Check(Near(t[0],s[8]) && Near(t[1],s[9]) && Near(t[2],s[12]) && Near(t[3],s[13]),"row major port extraction");
      Check(std::abs(t[0]) < 1e-12 && std::abs(t[3]) < 1e-12 && std::abs(t[1]) > .9,"cross fixture topology");
      const auto mid = b->fixture.Transfer(3.3125e9,"cross");
      Check(Near(mid[1],(b->fixture.samples[0].s[9]+b->fixture.samples[1].s[9])*.5),"complex interpolation");
      Check(std::abs(b->Gain(3.45e9)-b->Gain(3.55e9)) > 1e-15,"frequency-dependent coherent received PSD");
      Check(Near(b->Amplitude(3.5e9),b->Amplitude(3.5e9,true)),"DL/UL reciprocal amplitude");
      Reject([&]{b->Gain(3.29e9);});
      Reject([&]{b->Gain(3.71e9);});
    }
    Check(std::abs(v4.Gain(3.5e9)-v5.Gain(3.5e9)) > 1e-15,"candidate affects projected PSD");
    Bridge straight(v4Path,opPath,"straight");
    Check(std::abs(v4.Gain(3.5e9)-straight.Gain(3.5e9)) > 1e-15,"mapping affects PSD under declared projection");
    Check(Near(MaximumPowerGain(v4.fixture.Transfer(3.5e9,"cross")),
               MaximumPowerGain(v4.fixture.Transfer(3.5e9,"straight"))),"unitary mapping preserves maximum gain");
    const auto tc = v4.fixture.Transfer(3.5e9,"cross");
    const auto ts = v4.fixture.Transfer(3.5e9,"straight");
    Check(Near(std::norm(tc[0])+std::norm(tc[2]),std::norm(ts[0])+std::norm(ts[2])),
          "complete receive-basis power invariant under service swap");
    const Matrix2 h{Complex(.1,.2),Complex(.03,-.2),Complex(.25,.07),Complex(-.1,.05)};
    const double inv = 1/std::sqrt(2.0);
    const Polarization p{inv,Complex(0,inv)}, q{.6,Complex(0,.8)};
    Check(Near(Project(h,p,q),Project(Transpose(h),Conjugate(q),Conjugate(p))),"elliptic reciprocal projection");
    Check(!Near(Project(h,p,q),Project(Transpose(h),q,p)),"unconjugated elliptic modes are not reciprocal ports");
    const Matrix2 u{inv,Complex(0,inv),Complex(0,inv),inv};
    const Matrix2 uh{inv,Complex(0,-inv),Complex(0,-inv),inv};
    auto rotate = [&](Polarization a) { return Polarization{u[0]*a[0]+u[1]*a[1],u[2]*a[0]+u[3]*a[1]}; };
    Check(Near(Project(h,p,q),Project(Multiply(u,Multiply(h,uh)),rotate(p),rotate(q))),"unitary coordinate covariance");
    v4.installation.tx=p; v4.installation.rx=q;
    Check(Near(v4.Amplitude(3.5e9),v4.Amplitude(3.5e9,true)),"bridge elliptic reciprocity");
    for (auto& row:v4.installation.samples)
    {
      row.donor=Scale(I,.1); row.service=Scale(I,.1);
      row.direct=Scale(v4.fixture.Transfer(3.5e9,"cross"),-.01);
    }
    Check(v4.Gain(3.5e9) < 1e-28,"direct/passive destructive complex superposition");
    for (auto& row:v4.installation.samples) row.direct=Scale(row.direct,-1);
    const double constructive=v4.Gain(3.5e9);
    for (auto& row:v4.installation.samples) row.direct={};
    Check(Near(constructive,4*v4.Gain(3.5e9)),"constructive amplitude doubles power quadruples");
    Reject([] { CheckContraction(Scale(I,1.1)); });
    std::array<Complex,16> bad{}; bad.fill(.4);
    Reject([&] { CheckFourPort(bad); }); // every column power <1, still nonpassive
    bad={}; bad[1]=.2;
    Reject([&] { CheckFourPort(bad); });
    Reject([] { Operators::Parse("frequency_hz\n"); });
    auto invalid = SyntheticOperators();
    auto at = invalid.find("tx_projection=1,0,0,0");
    invalid.replace(at,std::string("tx_projection=1,0,0,0").size(),"tx_projection=2,0,0,0");
    Reject([&] { Operators::Parse(invalid); });
    Reject([] { Touchstone4::Parse("# GHz S RI R 75\n"); });
    Reject([] { Touchstone4::Parse("[Version] 2.0\n"); });
    Reject([] { Number("nan"); });
    Reject([] { CsvNumbers("1,2,"); });
    // Synthetic reciprocal RI/MA/DB tables independently exercise parser phase and ordering.
    for (const auto* fmt : {"RI","MA","DB"})
    {
      std::ostringstream ss;
      ss << "# MHz S " << fmt << " R 50\n";
      for (int f : {3300,3700})
      {
        ss << f;
        for (int k=0;k<16;++k)
        {
          const bool pass=k==3||k==6||k==9||k==12;
          if (std::string(fmt)=="RI") ss << (pass ? " 0 0.5" : " 0 0");
          else if (std::string(fmt)=="MA") ss << (pass ? " 0.5 90" : " 0 0");
          else ss << (pass ? " -6.020599913279624 90" : " -400 0");
        }
        ss << '\n';
      }
      auto table=Touchstone4::Parse(ss.str());
      Check(Near(table.Transfer(3.5e9,"cross")[1],Complex(0,.5)),"RI/MA/DB phase parsing");
    }
    RunConfig cfg;
    Check(ComputeEffectivePenetrationLossDb(cfg)==5,"legacy default scalar unchanged");
    cfg.passiveModel=PassiveModelType::EM_COMPLEX;
    Check(ComputeEffectivePenetrationLossDb(cfg)==0,"no double scalar Tx attenuation");
    Reject([&]{ValidateRunConfig(cfg);});
    cfg.emTouchstonePath=v4Path; cfg.emOperatorsPath=opPath; cfg.speedKmph=0;
    ValidateRunConfig(cfg);
    cfg.numUes=2;
    Reject([&]{ValidateRunConfig(cfg);});
    std::cout << "PASS " << checks << " numerical/validation checks\n";
  }
  catch(const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
