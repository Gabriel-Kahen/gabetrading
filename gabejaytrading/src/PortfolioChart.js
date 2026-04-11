import React, { useState, useEffect } from 'react';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  LineElement,
  CategoryScale,
  LinearScale,
  PointElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';

ChartJS.register(
  LineElement,
  CategoryScale,
  LinearScale,
  PointElement,
  Title,
  Tooltip,
  Legend
);

function PortfolioChart({ data, onTradeSelect, highlightedTrade }) {
  const [isMobile, setIsMobile] = useState(false);
  const accentColor = '#32dba7';
  const highlightColor = '#f6c452';
  const gridColor = 'rgba(255, 255, 255, 0.08)';

  // Check screen orientation (or you can use a width threshold)
  useEffect(() => {
    const checkOrientation = () => {
      // Here we use portrait orientation as a proxy for mobile.
      setIsMobile(window.matchMedia('(orientation: portrait)').matches);
    };

    checkOrientation();
    window.addEventListener('resize', checkOrientation);
    return () => window.removeEventListener('resize', checkOrientation);
  }, []);

  const aggregatedByDay = {};
  data.forEach((item) => {
    if (item.time === 'Start') {
      aggregatedByDay.__start__ = {
        time: item.time,
        portfolio: item.portfolio,
        sortKey: -Infinity,
        label: 'Start',
      };
      return;
    }

    const parsedTime = new Date(item.time);
    if (Number.isNaN(parsedTime.getTime())) {
      return;
    }

    const dayKey = parsedTime.toISOString().split('T')[0];
    const sortKey = parsedTime.getTime();
    const label = parsedTime.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

    if (!aggregatedByDay[dayKey] || sortKey > aggregatedByDay[dayKey].sortKey) {
      aggregatedByDay[dayKey] = {
        time: item.time,
        portfolio: item.portfolio,
        sortKey,
        label,
      };
    }
  });

  const chartPoints = Object.values(aggregatedByDay).sort(
    (a, b) => a.sortKey - b.sortKey
  );

  const chartLabels = chartPoints.map((point) => point.label || point.time);
  const uniqueTimes = chartPoints.map((point) => point.time);
  const portfolioValues = chartPoints.map((point) => point.portfolio);

  const defaultColor = accentColor;
  const pointBackgroundColors = uniqueTimes.map((time) =>
    time === highlightedTrade ? highlightColor : defaultColor
  );

  const chartData = {
    labels: chartLabels,
    datasets: [
      {
        label: 'Portfolio Value',
        data: portfolioValues,
        fill: true,
        backgroundColor: 'rgba(50, 219, 167, 0.08)',
        borderColor: defaultColor,
        borderWidth: 3,
        tension: 0.3,
        // Adjust the dot size based on screen orientation
        //im testing again
        pointRadius: isMobile ? 3 : 6,
        pointHoverRadius: isMobile ? 4 : 8,
        pointBackgroundColor: pointBackgroundColors,
        pointBorderColor: '#0f162d',
        pointBorderWidth: 2,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    responsiveAnimationDuration: 0,
    interaction: {
      mode: 'nearest',
      intersect: true,
    },
    hover: {
      mode: 'nearest',
      intersect: true,
    },
    layout: {
      padding: {
        top: 8,
        bottom: 12,
        left: 6,
        right: 6,
      },
    },
    scales: {
      x: {
        ticks: {
          color: '#a3b5d6',
          maxRotation: 0,
          autoSkip: true,
          maxTicksLimit: isMobile ? 4 : 8,
        },
        grid: {
          display: false,
        },
      },
      y: {
        ticks: {
          color: '#a3b5d6',
          callback: (value) => `$${Number(value).toLocaleString()}`,
        },
        grid: {
          color: gridColor,
          drawBorder: false,
        },
      },
    },
    plugins: {
      legend: {
        display: false,
      },
      tooltip: {
        enabled: false,
      },
    },
    onClick: (event, elements) => {
      if (elements.length > 0) {
        const index = elements[0].index;
        const selectedTime = uniqueTimes[index];
        if (onTradeSelect) {
          onTradeSelect(selectedTime);
        }
      }
    },
  };

  return (
    <div className="chart-card">
      <div className="chart-header">
        <div>
          <div className="chart-eyebrow">Equity curve</div>
          <h2>Portfolio Performance</h2>
        </div>
        <div className="chart-legend">
          <span className="chart-legend-dot" aria-hidden="true" />
          <span>Portfolio value</span>
        </div>
      </div>
      <div className="chart-body">
        <Line data={chartData} options={options} />
      </div>
    </div>
  );
}

export default PortfolioChart;
