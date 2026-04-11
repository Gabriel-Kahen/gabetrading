import React, { useState, useEffect, useCallback } from 'react';
import Papa from 'papaparse';
import PortfolioChart from './PortfolioChart';
import Sidebar from './Sidebar';
import './index.css';

// Helper function to format dates as M/D/YYYY, hh:mm AM/PM in EST/EDT.
function formatDate(dateString) {
  const date = new Date(dateString);
  
  // Check if the date is after March 9th (not including March 9th itself)
  const year = date.getFullYear();
  const marchNinth = new Date(year, 2, 9, 23, 59, 59, 999); // End of March 9th
  
  // If after March 9th, subtract 4 hours (EDT), otherwise subtract 5 hours (EST)
  const hoursToSubtract = date > marchNinth ? 4 : 5;
  date.setHours(date.getHours() - hoursToSubtract);
  
  const options = {
    month: 'numeric',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: 'numeric',
    hour12: true
  };
  return date.toLocaleString('en-US', options);
}

function App() {
  const [trades, setTrades] = useState([]);
  const [portfolioHistory, setPortfolioHistory] = useState([]);
  const [selectedTradeTime, setSelectedTradeTime] = useState(null); 

  const CSV_URL = 'https://storage.googleapis.com/gabe-jay-stock/data/trade_log.csv';

  const processTrades = useCallback((data) => {
    let portfolio = 1000000;
    const history = [];
  
    history.push({ time: 'Start', portfolio });
  
    const processedTrades = data.map((row) => {
      const ticker = row.Stock;
      const rawBuyTime = row['Entry Time'];
      const rawSellTime = row['Exit Time'];
      const buyTime = formatDate(rawBuyTime);
      const sellTime = formatDate(rawSellTime);
      const buyPrice = parseFloat(row['Buy Price']);
      const sellPrice = parseFloat(row['Sell Price']);
      const investmentAmount = portfolio / 3;
      const shares = Math.floor(investmentAmount / buyPrice);
      const cost = shares * buyPrice;
      const proceeds = shares * sellPrice;
      const profit = proceeds - cost;
      const percentProfit = (profit / cost) * 100;
  
      portfolio += profit;
      history.push({ time: sellTime, portfolio });
  
      return {
        ticker,
        buyTime,
        buyPrice,
        sellTime,
        sellPrice,
        shares,
        cost,
        proceeds,
        profit,
        percentProfit
      };
    });
  
    setTrades(processedTrades);
    setPortfolioHistory(history);
  }, []);

  const fetchData = useCallback(async () => {
    try {
      const csvUrl = `${CSV_URL}?t=${Date.now()}`;
      const response = await fetch(csvUrl, { cache: "no-store" });      const csvData = await response.text();
      console.log(csvData)
      Papa.parse(csvData, {
        header: true,
        skipEmptyLines: true,
        complete: (results) => {
          processTrades(results.data);
        },
        error: (error) => {
          console.error('Error parsing CSV:', error);
        }
      });
    } catch (error) {
      console.error('Error fetching CSV data:', error);
    }
  }, [CSV_URL, processTrades]);

  useEffect(() => {
    document.title = 'gabejaytrading';
    fetchData();
    const interval = setInterval(fetchData, 1000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleTradeSelect = (time) => {
    setSelectedTradeTime(time);
  };

  return (
    <div className="app-shell">
      <div className="announcement-bar" role="status" aria-live="polite">
        <span className="status-dot" aria-hidden="true"></span>
        <div className="announcement-copy">
          <strong>Heads up:</strong> This experiment was shut down on 11/14/25.
          <span className="announcement-muted">Data remains available for review.</span>
        </div>
      </div>

      <div className="app-container">
        <div className="main-content">
          <PortfolioChart data={portfolioHistory} onTradeSelect={handleTradeSelect} />
        </div>
        <div className="sidebar">
          <Sidebar trades={trades} selectedTradeTime={selectedTradeTime} />
        </div>
      </div>
    </div>
  );
}

export default App;
