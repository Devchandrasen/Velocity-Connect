#pragma once
#include <string>
#include <fstream>
#include <filesystem>
#include <stdexcept>

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
