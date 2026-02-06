#pragma once
#include <string>
#include <fstream>
#include <cstdlib>

inline void EnsureDir(const std::string& dir)
{
  std::string cmd = "mkdir -p " + dir;
  (void)std::system(cmd.c_str());
}

inline void WriteCsvHeader(const std::string& path, const std::string& header)
{
  std::ofstream f(path, std::ios::out);
  f << header << "\n";
}

inline void AppendCsvLine(const std::string& path, const std::string& line)
{
  std::ofstream f(path, std::ios::out | std::ios::app);
  f << line << "\n";
}
