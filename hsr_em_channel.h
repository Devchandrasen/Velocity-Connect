#pragma once
// Standalone C++17 power-wave transfer algebra. No ns-3 or antenna-gain defaults.
#include <algorithm>
#include <array>
#include <cmath>
#include <cctype>
#include <complex>
#include <fstream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include <utility>

namespace hsr::em
{
using Complex = std::complex<double>;
using Matrix2 = std::array<Complex, 4>; // row-major, output row / input column
using Polarization = std::array<Complex, 2>;
using Position = std::array<double, 3>;
constexpr double Pi = 3.14159265358979323846;

inline void Require(bool ok, const std::string& message)
{
  if (!ok) throw std::invalid_argument("EM bridge: " + message);
}
inline std::string Trim(std::string s)
{
  const auto a = s.find_first_not_of(" \t\r\n");
  return a == std::string::npos ? "" : s.substr(a, s.find_last_not_of(" \t\r\n") - a + 1);
}
inline std::string ReadFile(const std::string& path)
{
  std::ifstream f(path, std::ios::binary);
  Require(bool(f), "cannot read " + path);
  std::ostringstream s;
  s << f.rdbuf();
  Require(!f.bad(), "failed reading " + path);
  return s.str();
}
inline double Number(const std::string& token)
{
  size_t used = 0;
  const double x = std::stod(token, &used);
  Require(used == token.size() && std::isfinite(x), "invalid finite number: " + token);
  return x;
}
inline std::vector<double> CsvNumbers(const std::string& line)
{
  std::vector<double> values;
  std::istringstream in(line);
  std::string cell;
  Require(!line.empty() && line.back() != ',', "empty CSV field");
  while (std::getline(in, cell, ',')) values.push_back(Number(Trim(cell)));
  return values;
}
inline Matrix2 Multiply(const Matrix2& a, const Matrix2& b)
{
  Matrix2 c{};
  for (size_t r = 0; r < 2; ++r)
    for (size_t k = 0; k < 2; ++k)
      for (size_t j = 0; j < 2; ++j) c[2*r+j] += a[2*r+k]*b[2*k+j];
  return c;
}
inline Matrix2 Transpose(Matrix2 h) { std::swap(h[1], h[2]); return h; }
inline Polarization Conjugate(Polarization p)
{
  for (auto& x : p) x = std::conj(x);
  return p;
}
inline double MaximumPowerGain(const Matrix2& h)
{
  const double a = std::norm(h[0]) + std::norm(h[2]);
  const double d = std::norm(h[1]) + std::norm(h[3]);
  const Complex b = std::conj(h[0])*h[1] + std::conj(h[2])*h[3];
  return (a+d+std::hypot(a-d, 2*std::abs(b))) / 2;
}
inline void CheckContraction(const Matrix2& h)
{
  const double g = MaximumPowerGain(h);
  Require(std::isfinite(g) && g <= 1.0 + 1e-8,
          "normalized transfer exceeds passive power bound; do not clip or invent gain");
}
inline Complex Project(const Matrix2& h, const Polarization& tx, const Polarization& rx)
{
  return std::conj(rx[0])*(h[0]*tx[0]+h[1]*tx[1]) +
         std::conj(rx[1])*(h[2]*tx[0]+h[3]*tx[1]);
}

struct TouchstoneSample
{
  double hz;
  std::array<Complex, 16> s;
};

// Check I-S^H*S positive definite after a small numerical tolerance is added.
// Checking individual |Sij| or only column powers is NOT a passivity test.
inline void CheckFourPort(const std::array<Complex, 16>& s)
{
  std::array<Complex, 16> l{};
  for (size_t i = 0; i < 4; ++i)
    for (size_t j = 0; j <= i; ++j)
    {
      Require(std::abs(s[4*i+j]-s[4*j+i]) <= 1e-8,
              "nonreciprocal four-port (S must equal transpose, not adjoint)");
      Complex a = i == j ? 1.0 + 1e-8 : 0.0;
      for (size_t k = 0; k < 4; ++k) a -= std::conj(s[4*k+i])*s[4*k+j];
      for (size_t k = 0; k < j; ++k) a -= l[4*i+k]*std::conj(l[4*j+k]);
      if (i == j)
      {
        Require(std::isfinite(a.real()) && a.real() > 0 && std::abs(a.imag()) < 1e-8,
                "four-port is not passive within 1e-8 power tolerance");
        l[4*i+j] = std::sqrt(a.real());
      }
      else l[4*i+j] = a/l[4*j+j];
    }
}

template<class Sample>
inline std::pair<size_t, double> Interval(const std::vector<Sample>& samples, double hz)
{
  Require(samples.size() >= 2 && std::isfinite(hz) &&
          hz >= samples.front().hz && hz <= samples.back().hz,
          "frequency outside input support (extrapolation is forbidden)");
  const auto it = std::upper_bound(samples.begin(), samples.end(), hz,
    [](double f, const Sample& s) { return f < s.hz; });
  const size_t i = it == samples.end() ? samples.size()-2 : (it-samples.begin())-1;
  return {i, (hz-samples[i].hz)/(samples[i+1].hz-samples[i].hz)};
}
template<size_t N>
inline std::array<Complex,N> Interpolate(const std::array<Complex,N>& a,
                                       const std::array<Complex,N>& b, double t)
{
  std::array<Complex,N> h{};
  for (size_t k = 0; k < N; ++k) h[k] = (1-t)*a[k]+t*b[k];
  return h;
}

struct Touchstone4
{
  std::string raw;
  std::vector<TouchstoneSample> samples;
  static Touchstone4 Parse(const std::string& contents)
  {
    Touchstone4 table;
    table.raw = contents;
    std::istringstream input(contents);
    std::string line, format;
    double scale = 0;
    std::vector<double> data;
    bool options = false;
    while (std::getline(input, line))
    {
      line = Trim(line.substr(0, line.find('!')));
      if (line.empty()) continue;
      Require(line[0] != '[', "only explicit Touchstone 1 full four-port syntax is supported");
      if (line[0] == '#')
      {
        Require(!options && data.empty(), "duplicate or late option line");
        std::transform(line.begin(), line.end(), line.begin(),
          [](unsigned char c) { return static_cast<char>(std::toupper(c)); });
        std::istringstream opt(line.substr(1));
        std::string units, parameter, r, z, extra;
        Require(bool(opt >> units >> parameter >> format >> r >> z) && !(opt >> extra),
                "require explicit '# unit S RI|MA|DB R 50' options");
        Require(parameter == "S" && r == "R" && Number(z) == 50,
                "only equal real 50-ohm power-wave reference ports are supported");
        Require(format == "RI" || format == "MA" || format == "DB", "unknown complex format");
        scale = units == "HZ" ? 1 : units == "KHZ" ? 1e3 : units == "MHZ" ? 1e6 : units == "GHZ" ? 1e9 : 0;
        Require(scale > 0, "unknown frequency unit");
        options = true;
      }
      else
      {
        Require(options, "data before options");
        std::istringstream row(line);
        std::string token;
        while (row >> token) data.push_back(Number(token));
      }
    }
    Require(options && data.size() >= 66 && data.size()%33 == 0, "incomplete four-port data");
    for (size_t i = 0; i < data.size(); i += 33)
    {
      TouchstoneSample sample{};
      sample.hz = data[i]*scale;
      Require(std::isfinite(sample.hz) && sample.hz > 0 &&
              (table.samples.empty() || sample.hz > table.samples.back().hz), "frequency grid must increase strictly");
      // Touchstone 3+ port ordering is ROW-major, unlike historical two-port ordering.
      for (size_t k = 0; k < 16; ++k)
      {
        const double a = data[i+1+2*k], b = data[i+2+2*k];
        Require(format != "MA" || a >= 0, "negative magnitude");
        sample.s[k] = format == "RI" ? Complex(a,b) :
          std::polar(format == "DB" ? std::pow(10,a/20) : a, b*Pi/180);
      }
      CheckFourPort(sample.s);
      table.samples.push_back(sample);
    }
    return table;
  }
  Matrix2 Transfer(double hz, const std::string& mapping) const
  {
    Require(mapping == "cross" || mapping == "straight", "mapping must be cross or straight");
    const auto [i,t] = Interval(samples,hz);
    const auto s = Interpolate(samples[i].s,samples[i+1].s,t);
    Matrix2 h{s[8],s[9],s[12],s[13]}; // S[service 3,4; donor 1,2]
    if (mapping == "straight")
    {
      // Counterfactual service-terminal swap of supplied CROSS fixture, not a new HFSS solve.
      std::swap(h[0],h[2]);
      std::swap(h[1],h[3]);
    }
    return h;
  }
};

inline std::string OperatorHeader()
{
  std::string s = "frequency_hz";
  for (const auto* name : {"d", "in", "out"})
    for (const auto* ij : {"00", "01", "10", "11"})
      s += ","+std::string(name)+ij+"_re,"+name+ij+"_im";
  return s;
}
struct OperatorSample
{
  double hz;
  Matrix2 direct, donor, service;
};
struct Operators
{
  std::string raw;
  std::map<std::string,std::string> metadata;
  std::vector<OperatorSample> samples;
  Polarization tx{}, rx{};
  Position gnb{}, ue{};
  static Operators Parse(const std::string& contents)
  {
    Operators o;
    o.raw = contents;
    std::istringstream input(contents);
    std::string line;
    bool header = false;
    while (std::getline(input,line))
    {
      line = Trim(line);
      if (line.empty()) continue;
      if (line[0] == '#')
      {
        const auto eq = line.find('=');
        Require(!header && eq != std::string::npos, "metadata must be key=value before header");
        const auto key = Trim(line.substr(1,eq-1));
        const auto value = Trim(line.substr(eq+1));
        Require(!value.empty() && o.metadata.emplace(key,value).second, "empty/duplicate metadata");
      }
      else if (!header)
      {
        Require(line == OperatorHeader(), "unexpected operator CSV header/order");
        header = true;
      }
      else
      {
        const auto v = CsvNumbers(line);
        Require(v.size() == 25, "operator row must have frequency and 12 complex entries");
        OperatorSample sample{};
        sample.hz = v[0];
        Require(sample.hz > 0 && (o.samples.empty() || sample.hz > o.samples.back().hz),
                "operator grid must increase strictly");
        size_t k = 1;
        for (auto* matrix : {&sample.direct,&sample.donor,&sample.service})
        {
          for (auto& z : *matrix) { z = {v[k],v[k+1]}; k += 2; }
          CheckContraction(*matrix);
        }
        o.samples.push_back(sample);
      }
    }
    Require(o.samples.size() >= 2, "at least two operator frequencies required");
    const std::vector<std::string> keys{"schema","provenance","evidence","normalization","basis",
      "gnb_position_m","ue_position_m","tx_projection","rx_projection"};
    Require(o.metadata.size() == keys.size(), "unknown or missing operator metadata");
    for (const auto& key : keys) Require(o.metadata.count(key), "missing metadata: "+key);
    Require(o.metadata.at("schema") == "hsr-em-operators-v1", "unsupported operator schema");
    Require(o.metadata.at("normalization") == "absolute_power_waves_50ohm", "absolute power-wave normalization required");
    Require(o.metadata.at("evidence") == "synthetic" || o.metadata.at("evidence") == "external_unvalidated",
            "evidence must be synthetic or external_unvalidated; calibration is not certified here");
    const std::array<std::pair<const char*, Polarization*>, 2> projections{{
      {"tx_projection", &o.tx}, {"rx_projection", &o.rx}}};
    for (const auto& item : projections)
    {
      const auto v = CsvNumbers(o.metadata.at(item.first));
      Require(v.size() == 4, "projection needs two complex components");
      *item.second = {Complex(v[0],v[1]),Complex(v[2],v[3])};
      Require(std::abs(std::norm((*item.second)[0])+std::norm((*item.second)[1])-1) < 1e-9,
              "projection must have unit power norm; implicit normalization forbidden");
    }
    const std::array<std::pair<const char*, Position*>, 2> positions{{
      {"gnb_position_m", &o.gnb}, {"ue_position_m", &o.ue}}};
    for (const auto& item : positions)
    {
      const auto v = CsvNumbers(o.metadata.at(item.first));
      Require(v.size() == 3, "position requires x,y,z metres");
      std::copy(v.begin(),v.end(),item.second->begin());
    }
    return o;
  }
  OperatorSample At(double hz) const
  {
    const auto [i,t] = Interval(samples,hz);
    return {hz,Interpolate(samples[i].direct,samples[i+1].direct,t),
      Interpolate(samples[i].donor,samples[i+1].donor,t),
      Interpolate(samples[i].service,samples[i+1].service,t)};
  }
};

struct Bridge
{
  Touchstone4 fixture;
  Operators installation;
  std::string mapping;
  Bridge(const std::string& fixturePath, const std::string& operatorPath, const std::string& m)
    : fixture(Touchstone4::Parse(ReadFile(fixturePath))),
      installation(Operators::Parse(ReadFile(operatorPath))), mapping(m)
  {
    Require(mapping == "cross" || mapping == "straight", "mapping must be cross or straight");
  }
  Matrix2 Total(double hz, bool reverse = false) const
  {
    const auto o = installation.At(hz);
    Matrix2 h = Multiply(o.service,Multiply(fixture.Transfer(hz,mapping),o.donor));
    for (size_t k = 0; k < 4; ++k) h[k] += o.direct[k];
    CheckContraction(h); // fail, never cap a physically inconsistent coherent sum
    return reverse ? Transpose(h) : h;
  }
  Complex Amplitude(double hz, bool reverse = false) const
  {
    // Reciprocal antenna modes exchange and conjugate TX/RX Jones vectors.
    // H_reverse=H_forward^T, never H^H. Arbitrary independent UL vectors need not give equal powers.
    return reverse ? Project(Total(hz,true),Conjugate(installation.rx),Conjugate(installation.tx)) :
                     Project(Total(hz),installation.tx,installation.rx);
  }
  double Gain(double hz, bool reverse = false) const { return std::norm(Amplitude(hz,reverse)); }
  void ValidateRange(double lo, double hi) const
  {
    Require(lo < hi, "invalid occupied band");
    for (double f : {lo,hi}) { (void)Total(f); }
    // Knot checks plus every actual ns-3 RB centre at runtime. This does not prove broadband causality.
    for (const auto& s : fixture.samples) if (s.hz >= lo && s.hz <= hi) (void)Total(s.hz);
    for (const auto& s : installation.samples) if (s.hz >= lo && s.hz <= hi) (void)Total(s.hz);
  }
};
} // namespace hsr::em
