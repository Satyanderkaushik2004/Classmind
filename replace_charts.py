vyom_html_path = r"c:\Users\ADMIN\Downloads\Classmind-main\vyom.html"

with open(vyom_html_path, "r", encoding="utf-8") as f:
    content = f.read()

# Upgraded BarChart (first one)
old_bar_chart_1 = """function BarChart({
  labels,
  data,
  label = 'Value',
  color
}) {
  const ref = useRef(null);
  const chartRef = useRef(null);
  useEffect(() => {
    if (!ref.current) return;
    const c = color || getComputedAccent();
    chartRef.current?.destroy();
    chartRef.current = new Chart(ref.current, {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          label,
          data,
          backgroundColor: c + '99',
          borderColor: c,
          borderWidth: 1,
          borderRadius: 6
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: false
          }
        },
        scales: {
          x: {
            grid: {
              color: '#2A2A2A'
            },
            ticks: {
              color: '#8F8F8F'
            }
          },
          y: {
            grid: {
              color: '#2A2A2A'
            },
            ticks: {
              color: '#8F8F8F'
            },
            beginAtZero: true
          }
        }
      }
    });
    return () => chartRef.current?.destroy();
  }, [labels, data]);
  return /*#__PURE__*/React.createElement("div", {
    className: "chart-container"
  }, /*#__PURE__*/React.createElement("canvas", {
    ref: ref
  }));
}"""

new_bar_chart_1 = """function BarChart({
  labels,
  data,
  label = 'Value',
  color
}) {
  const ref = useRef(null);
  const chartRef = useRef(null);
  const { language } = React.useContext(AppCtx) || { language: 'en' };
  useEffect(() => {
    if (!ref.current) return;
    const c = color || getComputedAccent();
    chartRef.current?.destroy();
    const translatedLabels = labels ? labels.map(l => translateString(l, language)) : labels;
    const translatedLabel = label ? translateString(label, language) : label;
    chartRef.current = new Chart(ref.current, {
      type: 'bar',
      data: {
        labels: translatedLabels,
        datasets: [{
          label: translatedLabel,
          data,
          backgroundColor: c + '99',
          borderColor: c,
          borderWidth: 1,
          borderRadius: 6
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: false
          }
        },
        scales: {
          x: {
            grid: {
              color: '#2A2A2A'
            },
            ticks: {
              color: '#8F8F8F'
            }
          },
          y: {
            grid: {
              color: '#2A2A2A'
            },
            ticks: {
              color: '#8F8F8F'
            },
            beginAtZero: true
          }
        }
      }
    });
    return () => chartRef.current?.destroy();
  }, [labels, data, color, language]);
  return /*#__PURE__*/React.createElement("div", {
    className: "chart-container"
  }, /*#__PURE__*/React.createElement("canvas", {
    ref: ref
  }));
}"""

# Upgraded DoughnutChart
old_doughnut_chart = """function DoughnutChart({
  labels,
  data,
  colors
}) {
  const ref = useRef(null);
  const chartRef = useRef(null);
  useEffect(() => {
    if (!ref.current) return;
    const a  = getComputedAccent();
    const a2 = getComputedAccent2();
    chartRef.current?.destroy();
    chartRef.current = new Chart(ref.current, {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{
          data,
          backgroundColor: colors || [a, a2, a + 'CC', a2 + 'CC', '#4A4A4A', '#2A2A2A'],
          borderWidth: 0,
          hoverOffset: 4
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '65%',
        plugins: {
          legend: {
            position: 'right',
            labels: {
              color: '#e2e8f0',
              padding: 12
            }
          }
        }
      }
    });
    return () => chartRef.current?.destroy();
  }, [labels, data]);
  return /*#__PURE__*/React.createElement("div", {
    className: "chart-container"
  }, /*#__PURE__*/React.createElement("canvas", {
    ref: ref
  }));
}"""

new_doughnut_chart = """function DoughnutChart({
  labels,
  data,
  colors
}) {
  const ref = useRef(null);
  const chartRef = useRef(null);
  const { language } = React.useContext(AppCtx) || { language: 'en' };
  useEffect(() => {
    if (!ref.current) return;
    const a  = getComputedAccent();
    const a2 = getComputedAccent2();
    chartRef.current?.destroy();
    const translatedLabels = labels ? labels.map(l => translateString(l, language)) : labels;
    chartRef.current = new Chart(ref.current, {
      type: 'doughnut',
      data: {
        labels: translatedLabels,
        datasets: [{
          data,
          backgroundColor: colors || [a, a2, a + 'CC', a2 + 'CC', '#4A4A4A', '#2A2A2A'],
          borderWidth: 0,
          hoverOffset: 4
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '65%',
        plugins: {
          legend: {
            position: 'right',
            labels: {
              color: '#e2e8f0',
              padding: 12
            }
          }
        }
      }
    });
    return () => chartRef.current?.destroy();
  }, [labels, data, colors, language]);
  return /*#__PURE__*/React.createElement("div", {
    className: "chart-container"
  }, /*#__PURE__*/React.createElement("canvas", {
    ref: ref
  }));
}"""

# Upgraded BarChart (second one)
old_bar_chart_2 = """function BarChart({
  labels,
  data,
  label = 'Value',
  color = '#22c55e'
}) {
  const ref = useRef(null);
  const chartRef = useRef(null);
  useEffect(() => {
    if (!ref.current) return;
    chartRef.current?.destroy();
    chartRef.current = new Chart(ref.current, {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          label,
          data,
          backgroundColor: color,
          borderRadius: 4,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: false
          }
        },
        scales: {
          x: {
            grid: {
              display: false
            },
            ticks: {
              color: '#8F8F8F'
            }
          },
          y: {
            grid: {
              color: '#2A2A2A'
            },
            ticks: {
              color: '#8F8F8F'
            },
            beginAtZero: true
          }
        }
      }
    });
    return () => chartRef.current?.destroy();
  }, [labels, data]);
  return /*#__PURE__*/React.createElement("div", {
    className: "chart-container"
  }, /*#__PURE__*/React.createElement("canvas", {
    ref: ref
  }));
}"""

new_bar_chart_2 = """function BarChart({
  labels,
  data,
  label = 'Value',
  color = '#22c55e'
}) {
  const ref = useRef(null);
  const chartRef = useRef(null);
  const { language } = React.useContext(AppCtx) || { language: 'en' };
  useEffect(() => {
    if (!ref.current) return;
    chartRef.current?.destroy();
    const translatedLabels = labels ? labels.map(l => translateString(l, language)) : labels;
    const translatedLabel = label ? translateString(label, language) : label;
    chartRef.current = new Chart(ref.current, {
      type: 'bar',
      data: {
        labels: translatedLabels,
        datasets: [{
          label: translatedLabel,
          data,
          backgroundColor: color,
          borderRadius: 4,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: false
          }
        },
        scales: {
          x: {
            grid: {
              display: false
            },
            ticks: {
              color: '#8F8F8F'
            }
          },
          y: {
            grid: {
              color: '#2A2A2A'
            },
            ticks: {
              color: '#8F8F8F'
            },
            beginAtZero: true
          }
        }
      }
    });
    return () => chartRef.current?.destroy();
  }, [labels, data, color, language]);
  return /*#__PURE__*/React.createElement("div", {
    className: "chart-container"
  }, /*#__PURE__*/React.createElement("canvas", {
    ref: ref
  }));
}"""

# Upgraded LineChart
old_line_chart = """function LineChart({
  labels,
  data,
  label = 'Score'
}) {
  const ref = useRef(null);
  const chartRef = useRef(null);
  useEffect(() => {
    if (!ref.current) return;
    const accentColor = getComputedAccent();
    const rgb = getComputedAccentRgb();
    const glowColor = `rgba(${rgb}, 0.025)`;
    chartRef.current?.destroy();
    chartRef.current = new Chart(ref.current, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label,
          data,
          borderColor: accentColor,
          backgroundColor: glowColor,
          fill: true,
          tension: 0.4,
          pointRadius: 4,
          pointBackgroundColor: accentColor
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: false
          }
        },
        scales: {
          x: {
            grid: {
              color: '#2A2A2A'
            },
            ticks: {
              color: '#8F8F8F'
            }
          },
          y: {
            grid: {
              color: '#2A2A2A'
            },
            ticks: {
              color: '#8F8F8F'
            },
            beginAtZero: true
          }
        }
      }
    });
    return () => chartRef.current?.destroy();
  }, [labels, data]);
  return /*#__PURE__*/React.createElement("div", {
    className: "chart-container"
  }, /*#__PURE__*/React.createElement("canvas", {
    ref: ref
  }));
}"""

new_line_chart = """function LineChart({
  labels,
  data,
  label = 'Score'
}) {
  const ref = useRef(null);
  const chartRef = useRef(null);
  const { language } = React.useContext(AppCtx) || { language: 'en' };
  useEffect(() => {
    if (!ref.current) return;
    const accentColor = getComputedAccent();
    const rgb = getComputedAccentRgb();
    const glowColor = `rgba(${rgb}, 0.025)`;
    chartRef.current?.destroy();
    const translatedLabels = labels ? labels.map(l => translateString(l, language)) : labels;
    const translatedLabel = label ? translateString(label, language) : label;
    chartRef.current = new Chart(ref.current, {
      type: 'line',
      data: {
        labels: translatedLabels,
        datasets: [{
          label: translatedLabel,
          data,
          borderColor: accentColor,
          backgroundColor: glowColor,
          fill: true,
          tension: 0.4,
          pointRadius: 4,
          pointBackgroundColor: accentColor
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: false
          }
        },
        scales: {
          x: {
            grid: {
              color: '#2A2A2A'
            },
            ticks: {
              color: '#8F8F8F'
            }
          },
          y: {
            grid: {
              color: '#2A2A2A'
            },
            ticks: {
              color: '#8F8F8F'
            },
            beginAtZero: true,
            max: 100
          }
        }
      }
    });
    return () => chartRef.current?.destroy();
  }, [labels, data, language]);
  return /*#__PURE__*/React.createElement("div", {
    className: "chart-container"
  }, /*#__PURE__*/React.createElement("canvas", {
    ref: ref
  }));
}"""

# Upgraded RptLineChart
old_rpt_line_chart = """function RptLineChart({ labels, datasets, height }) {
  const ref = React.useRef(null);
  const chartRef = React.useRef(null);
  const gridColor = 'rgba(var(--accent-rgb), 0.06)';
  const tickColor = '#8F8F8F';
  const warmDatasets = datasets.map((ds, i) => {
    const palette = [getComputedAccent(), getComputedAccent2(), '#C2410C', '#FFB366', '#4A4A4A', '#2A2A2A'];
    const dc = palette[i % palette.length];
    return { ...ds, borderColor: ds.borderColor || dc, backgroundColor: (ds.backgroundColor || dc) + '22', pointBackgroundColor: ds.pointBackgroundColor || dc };
  });
  React.useEffect(() => {
    if (!ref.current) return;
    chartRef.current?.destroy();
    chartRef.current = new Chart(ref.current, {
      type: 'line',
      data: { labels, datasets: warmDatasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: datasets.length > 1, labels: { color: tickColor, boxWidth: 12, font: { size: 11 } } } },
        scales: {
          x: { grid: { color: gridColor }, ticks: { color: tickColor, font: { size: 10 } } },
          y: { grid: { color: gridColor }, ticks: { color: tickColor, font: { size: 10 } }, beginAtZero: true, max: 100 }
        }
      }
    });
    return () => chartRef.current?.destroy();
  }, [JSON.stringify(labels), JSON.stringify(datasets)]);
  return React.createElement('div', { style: { height: height || 200 } },
    React.createElement('canvas', { ref })
  );
}"""

new_rpt_line_chart = """function RptLineChart({ labels, datasets, height }) {
  const ref = React.useRef(null);
  const chartRef = React.useRef(null);
  const { language } = React.useContext(AppCtx) || { language: 'en' };
  const gridColor = 'rgba(var(--accent-rgb), 0.06)';
  const tickColor = '#8F8F8F';
  const warmDatasets = datasets.map((ds, i) => {
    const palette = [getComputedAccent(), getComputedAccent2(), '#C2410C', '#FFB366', '#4A4A4A', '#2A2A2A'];
    const dc = palette[i % palette.length];
    const dsLabel = ds.label ? translateString(ds.label, language) : ds.label;
    return { ...ds, label: dsLabel, borderColor: ds.borderColor || dc, backgroundColor: (ds.backgroundColor || dc) + '22', pointBackgroundColor: ds.pointBackgroundColor || dc };
  });
  React.useEffect(() => {
    if (!ref.current) return;
    chartRef.current?.destroy();
    const translatedLabels = labels ? labels.map(l => translateString(l, language)) : labels;
    chartRef.current = new Chart(ref.current, {
      type: 'line',
      data: { labels: translatedLabels, datasets: warmDatasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: datasets.length > 1, labels: { color: tickColor, boxWidth: 12, font: { size: 11 } } } },
        scales: {
          x: { grid: { color: gridColor }, ticks: { color: tickColor, font: { size: 10 } } },
          y: { grid: { color: gridColor }, ticks: { color: tickColor, font: { size: 10 } }, beginAtZero: true, max: 100 }
        }
      }
    });
    return () => chartRef.current?.destroy();
  }, [JSON.stringify(labels), JSON.stringify(datasets), language]);
  return React.createElement('div', { style: { height: height || 200 } },
    React.createElement('canvas', { ref })
  );
}"""

# Upgraded RptBarChart
old_rpt_bar_chart = """function RptBarChart({ labels, datasets, height, stacked, maxY }) {
  const ref = React.useRef(null);
  const chartRef = React.useRef(null);
  const gridColor = 'rgba(var(--accent-rgb), 0.06)';
  const tickColor = '#8F8F8F';
  const warmDatasets = datasets.map((ds, i) => {
    const palette = [getComputedAccent(), getComputedAccent2(), '#C2410C', '#FFB366', '#4A4A4A', '#2A2A2A'];
    const dc = palette[i % palette.length];
    return { ...ds, backgroundColor: ds.backgroundColor || (dc + 'BB'), borderColor: ds.borderColor || dc, borderWidth: 1 };
  });
  React.useEffect(() => {
    if (!ref.current) return;
    chartRef.current?.destroy();
    chartRef.current = new Chart(ref.current, {
      type: 'bar',
      data: { labels, datasets: warmDatasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: datasets.length > 1, labels: { color: tickColor, boxWidth: 12, font: { size: 11 } } } },
        scales: {
          x: { grid: { display: false }, ticks: { color: tickColor, font: { size: 10 } }, stacked: !!stacked },
          y: { grid: { color: gridColor }, ticks: { color: tickColor, font: { size: 10 } }, beginAtZero: true, stacked: !!stacked, max: maxY }
        }
      }
    });
    return () => chartRef.current?.destroy();
  }, [JSON.stringify(labels), JSON.stringify(datasets)]);
  return React.createElement('div', { style: { height: height || 200 } },
    React.createElement('canvas', { ref })
  );
}"""

new_rpt_bar_chart = """function RptBarChart({ labels, datasets, height, stacked, maxY }) {
  const ref = React.useRef(null);
  const chartRef = React.useRef(null);
  const { language } = React.useContext(AppCtx) || { language: 'en' };
  const gridColor = 'rgba(var(--accent-rgb), 0.06)';
  const tickColor = '#8F8F8F';
  const warmDatasets = datasets.map((ds, i) => {
    const palette = [getComputedAccent(), getComputedAccent2(), '#C2410C', '#FFB366', '#4A4A4A', '#2A2A2A'];
    const dc = palette[i % palette.length];
    const dsLabel = ds.label ? translateString(ds.label, language) : ds.label;
    return { ...ds, label: dsLabel, backgroundColor: ds.backgroundColor || (dc + 'BB'), borderColor: ds.borderColor || dc, borderWidth: 1 };
  });
  React.useEffect(() => {
    if (!ref.current) return;
    chartRef.current?.destroy();
    const translatedLabels = labels ? labels.map(l => translateString(l, language)) : labels;
    chartRef.current = new Chart(ref.current, {
      type: 'bar',
      data: { labels: translatedLabels, datasets: warmDatasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: datasets.length > 1, labels: { color: tickColor, boxWidth: 12, font: { size: 11 } } } },
        scales: {
          x: { grid: { display: false }, ticks: { color: tickColor, font: { size: 10 } }, stacked: !!stacked },
          y: { grid: { color: gridColor }, ticks: { color: tickColor, font: { size: 10 } }, beginAtZero: true, stacked: !!stacked, max: maxY }
        }
      }
    });
    return () => chartRef.current?.destroy();
  }, [JSON.stringify(labels), JSON.stringify(datasets), language]);
  return React.createElement('div', { style: { height: height || 200 } },
    React.createElement('canvas', { ref })
  );
}"""

# Upgraded RptDoughnutChart
old_rpt_doughnut_chart = """function RptDoughnutChart({ labels, data, colors, height }) {
  const ref = React.useRef(null);
  const chartRef = React.useRef(null);
  React.useEffect(() => {
    if (!ref.current) return;
    chartRef.current?.destroy();
    const a = getComputedAccent();
    const a2 = getComputedAccent2();
    const defaultColors = colors || [a, a2, '#C2410C', '#FFB366', '#4A4A4A', '#2A2A2A'];
    chartRef.current = new Chart(ref.current, {
      type: 'doughnut',
      data: { labels, datasets: [{ data, backgroundColor: defaultColors, borderWidth: 0, hoverOffset: 6 }] },
      options: {
        responsive: true, maintainAspectRatio: false, cutout: '68%',
        plugins: { legend: { position: 'right', labels: { color: '#8F8F8F', padding: 10, font: { size: 11 } } } }
      }
    });
    return () => chartRef.current?.destroy();
  }, [JSON.stringify(data)]);
  return React.createElement('div', { style: { height: height || 200 } },
    React.createElement('canvas', { ref })
  );
}"""

new_rpt_doughnut_chart = """function RptDoughnutChart({ labels, data, colors, height }) {
  const ref = React.useRef(null);
  const chartRef = React.useRef(null);
  const { language } = React.useContext(AppCtx) || { language: 'en' };
  React.useEffect(() => {
    if (!ref.current) return;
    chartRef.current?.destroy();
    const a = getComputedAccent();
    const a2 = getComputedAccent2();
    const defaultColors = colors || [a, a2, '#C2410C', '#FFB366', '#4A4A4A', '#2A2A2A'];
    const translatedLabels = labels ? labels.map(l => translateString(l, language)) : labels;
    chartRef.current = new Chart(ref.current, {
      type: 'doughnut',
      data: { labels: translatedLabels, datasets: [{ data, backgroundColor: defaultColors, borderWidth: 0, hoverOffset: 6 }] },
      options: {
        responsive: true, maintainAspectRatio: false, cutout: '68%',
        plugins: { legend: { position: 'right', labels: { color: '#8F8F8F', padding: 10, font: { size: 11 } } } }
      }
    });
    return () => chartRef.current?.destroy();
  }, [JSON.stringify(data), JSON.stringify(labels), language]);
  return React.createElement('div', { style: { height: height || 200 } },
    React.createElement('canvas', { ref })
  );
}"""

def replace_exact(old_code, new_code):
    global content
    if old_code in content:
        content = content.replace(old_code, new_code)
        print("Replaced one chart wrapper block.")
    else:
        # Standardize CRLF and spaces to check
        norm_old = old_code.replace("\\r\\n", "\\n").strip()
        norm_content = content.replace("\\r\\n", "\\n")
        if norm_old in norm_content:
            # Reconstruct content
            content = norm_content.replace(norm_old, new_code.replace("\\r\\n", "\\n"))
            print("Replaced one chart wrapper block after CRLF normalization.")
        else:
            print("Could not find chart wrapper block.")

replace_exact(old_bar_chart_1, new_bar_chart_1)
replace_exact(old_doughnut_chart, new_doughnut_chart)
replace_exact(old_bar_chart_2, new_bar_chart_2)
replace_exact(old_line_chart, new_line_chart)
replace_exact(old_rpt_line_chart, new_rpt_line_chart)
replace_exact(old_rpt_bar_chart, new_rpt_bar_chart)
replace_exact(old_rpt_doughnut_chart, new_rpt_doughnut_chart)

with open(vyom_html_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Replacement complete.")
