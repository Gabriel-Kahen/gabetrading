import React, { useState, useEffect, useRef, useMemo } from 'react';

function Sidebar({ trades, selectedTradeTime }) {
  const sortedTrades = useMemo(
    () => [...trades].sort((a, b) => new Date(b.sellTime) - new Date(a.sellTime)),
    [trades]
  );

//not loaded into trades

  const tradesByDate = useMemo(() => {
    return sortedTrades.reduce((acc, trade) => {
      const dateKey = new Date(trade.sellTime).toLocaleDateString('en-US');
      if (!acc[dateKey]) acc[dateKey] = [];
      acc[dateKey].push(trade);
      return acc;
    }, {});
  }, [sortedTrades]);

  const tradeDates = useMemo(() => Object.keys(tradesByDate), [tradesByDate]);

  const [currentIndex, setCurrentIndex] = useState(0);
  const [highlightedTrade, setHighlightedTrade] = useState(null);
  const tradeRefs = useRef({});

  const [ignoreChartSelection, setIgnoreChartSelection] = useState(false);
  const lastSelectedTradeRef = useRef(null);

  useEffect(() => {
    if (selectedTradeTime !== lastSelectedTradeRef.current) {
      setIgnoreChartSelection(false);
      lastSelectedTradeRef.current = selectedTradeTime;
    }
  }, [selectedTradeTime]);


  
  useEffect(() => {
    if (selectedTradeTime && !ignoreChartSelection) {
      const selectedDate = tradeDates.find(date =>
        tradesByDate[date].some(trade => trade.sellTime === selectedTradeTime)
      );

      if (selectedDate) {
        const newIndex = tradeDates.indexOf(selectedDate);
        setCurrentIndex(newIndex);
      }
    }
  }, [selectedTradeTime, tradeDates, tradesByDate, ignoreChartSelection]);


  
  const currentDate = tradeDates[currentIndex];
  const currentTrades = tradesByDate[currentDate] || [];
  const groupedTrades = [];
  for (let i = 0; i < currentTrades.length; i +=3) {
    const group = currentTrades.slice(i, i + 3);
    const buyTimes = group.map(trade => new Date(trade.buyTime));
    const sellTimes = group.map(trade => new Date(trade.sellTime));

    const earliestBuyTime = new Date(Math.min(...buyTimes)).toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: 'numeric',
      hour12: true
    });
    const latestSellTime = new Date(Math.max(...sellTimes)).toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: 'numeric',
      hour12: true
    });

    groupedTrades.push({
      trades: group,
      holdingPeriod: `${earliestBuyTime} → ${latestSellTime}`,
      id: group[group.length - 1].sellTime,
      tradeKeys: group.map((trade) => trade.sellTime),
    });
  }

  const scrollTimeoutRef = useRef(null);
  const highlightTimeoutRef = useRef(null);

  useEffect(() => {
    if (scrollTimeoutRef.current) {
      clearTimeout(scrollTimeoutRef.current);
    }
    if (highlightTimeoutRef.current) {
      clearTimeout(highlightTimeoutRef.current);
    }

    if (selectedTradeTime) {
      scrollTimeoutRef.current = setTimeout(() => {
        if (tradeRefs.current[selectedTradeTime]) {
          tradeRefs.current[selectedTradeTime].scrollIntoView({ behavior: 'smooth', block: 'center' });
          setHighlightedTrade(selectedTradeTime);

          highlightTimeoutRef.current = setTimeout(() => {
            setHighlightedTrade(null);
          }, 2000);
        }
      }, 300);
    }

    return () => {
      clearTimeout(scrollTimeoutRef.current);
      clearTimeout(highlightTimeoutRef.current);
    };
  }, [selectedTradeTime]);

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: '6px', color: 'var(--text-primary)' }}>
      {/* Scrollable Main Content */}
      <div style={{ overflowY: 'auto', flex: 1, paddingBottom: '12px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {/* Sticky Header */}
        <div 
          style={{
            position: 'sticky',
            top: 0,
            backgroundColor: 'var(--panel)',
            zIndex: 10,
            padding: '10px 10px 12px',
            borderBottom: '1px solid var(--border)',
            textAlign: 'center',
            boxShadow: '0 12px 24px rgba(0, 0, 0, 0.25)'
          }}
        >
          <h2 style={{ margin: '0', fontSize: '1.5rem' }}>Trade Details</h2>
          <h3 style={{ margin: '4px 0 0', fontSize: '1.1rem', color: 'var(--text-muted)' }}>{currentDate}</h3>
        </div>

        {/* Trade Groups */}
        {groupedTrades.map((group, index) => (
          <div
            key={index}
            ref={(el) => {
              if (!el) return;
              group.tradeKeys.forEach((key) => {
                tradeRefs.current[key] = el;
              });
            }}
            onMouseEnter={() => setHighlightedTrade(group.id)}
            onMouseLeave={() => setHighlightedTrade(null)}
            style={{
              border: `1px solid ${group.tradeKeys.includes(highlightedTrade) ? 'rgba(50, 219, 167, 0.45)' : 'var(--border)'}`,
              padding: '12px',
              marginBottom: '4px',
              borderRadius: '12px',
              backgroundColor: group.tradeKeys.includes(highlightedTrade) ? 'rgba(50, 219, 167, 0.08)' : 'rgba(255, 255, 255, 0.02)',
              transition: 'background-color 0.25s ease-in-out, border-color 0.25s ease-in-out',
              boxShadow: '0 12px 32px rgba(2, 10, 30, 0.35)'
            }}
          >
            <strong style={{ color: 'var(--text-primary)' }}>Holding Period: {group.holdingPeriod}</strong>
            <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '5px', fontSize: '0.95rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  <th style={{ textAlign: 'left', padding: '6px 5px', color: 'var(--text-muted)' }}>Stock</th>
                  <th style={{ textAlign: 'right', padding: '6px 5px', color: 'var(--text-muted)' }}>Buy Price</th>
                  <th style={{ textAlign: 'right', padding: '6px 5px', color: 'var(--text-muted)' }}>Sell Price</th>
                  <th style={{ textAlign: 'right', padding: '6px 5px', color: 'var(--text-muted)' }}>% Profit</th>
                </tr>
              </thead>
              <tbody>
                {group.trades.map((trade, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                    <td style={{ padding: '6px 5px' }}><strong>{trade.ticker}</strong></td>
                    <td style={{ padding: '6px 5px', textAlign: 'right', color: 'var(--text-primary)' }}>${trade.buyPrice.toFixed(2)}</td>
                    <td style={{ padding: '6px 5px', textAlign: 'right', color: 'var(--text-primary)' }}>${trade.sellPrice.toFixed(2)}</td>
                    <td
                      style={{
                        padding: '6px 5px',
                        textAlign: 'right',
                        color: trade.percentProfit >= 0 ? '#32dba7' : '#f87171',
                        fontWeight: 700
                      }}
                    >
                      {trade.percentProfit.toFixed(2)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </div>

      {/* Footer Navigation inside Sidebar */}
      <div
        style={{
          backgroundColor: 'var(--panel)',
          borderTop: '1px solid var(--border)',
          paddingTop: '15px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '10px'
        }}
      >
        <button
          onClick={() => {
            setIgnoreChartSelection(true);
            setCurrentIndex(prev => Math.max(0, prev - 1));
          }}
          disabled={currentIndex === 0}
        >
          Next Day
        </button>
        
        <span>{currentIndex + 1} / {tradeDates.length}</span>
        
        <button 
          onClick={() => {
            setIgnoreChartSelection(true);
            setCurrentIndex(prev => Math.min(tradeDates.length - 1, prev + 1));
          }}
          disabled={currentIndex === tradeDates.length - 1}
        >
          Previous Day
        </button>
      </div>
    </div>
  );
}

export default Sidebar;
