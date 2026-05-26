import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { fetchPriceHistory } from '../api';

const COLORS = [
  '#d4a754', '#c0392b', '#2c3e50', '#27ae60', '#8e44ad',
  '#e67e22', '#2980b9', '#16a085', '#d35400', '#7f8c8d',
  '#1abc9c', '#9b59b6', '#f39c12', '#e74c3c', '#34495e',
];

function variantLabel(v) {
  return `${v.source_name} ${v.box_label}`;
}

export default function CigarDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [days, setDays] = useState(30);

  useEffect(() => {
    if (!id || id === 'undefined') {
      setError('无效的雪茄ID');
      setLoading(false);
      return;
    }
    setLoading(true);
    fetchPriceHistory(id, days)
      .then(d => { setData(d); setLoading(false); })
      .catch(() => { setError('数据加载失败'); setLoading(false); });
  }, [id, days]);

  if (loading) {
    return (
      <div className="loading-state">
        <div className="spinner" />
        <p>加载中…</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="error-state">
        <p>{error || '数据加载失败'}</p>
        <button onClick={() => navigate('/')}>返回仪表盘</button>
      </div>
    );
  }

  const variants = data.variants || [];
  const chartData = buildChartData(variants);

  return (
    <div className="cigar-detail">
      <button className="back-btn" onClick={() => navigate('/')}>
        ← 返回
      </button>

      <div className="detail-header">
        {data.cigar_brand && (
          <span className="brand-badge">{data.cigar_brand}</span>
        )}
        <h2>{data.cigar_name || `Cigar #${data.cigar_id}`}</h2>
        {data.cigar_name_en && data.cigar_name_en !== data.cigar_name && (
          <span className="sub-name">{data.cigar_name_en}</span>
        )}
      </div>

      {/* 无数据 */}
      {variants.length === 0 && (
        <div className="empty-state">
          <p>📭 该雪茄暂无价格记录</p>
          <p className="hint">等下次爬虫抓取后数据就会出现在这里</p>
        </div>
      )}

      {/* Variant Cards —— 每个来源+包装一个卡片 */}
      {variants.length > 0 && (
        <div className="variant-grid">
          {variants.map((v, i) => {
            const points = v.points || [];
            const latest = points[points.length - 1];
            const min = points.length ? Math.min(...points.map(p => p.price)) : null;
            const max = points.length ? Math.max(...points.map(p => p.price)) : null;
            return (
              <div
                key={`${v.source_slug}__${v.box_size}`}
                className="variant-card"
                style={{ borderLeftColor: COLORS[i % COLORS.length] }}
              >
                <div className="variant-card-header">
                  <span className="variant-source">{v.source_name}</span>
                  <span className="variant-box-tag">{v.box_label}</span>
                </div>
                {latest ? (
                  <div className="variant-stats">
                    <div className="vs-item">
                      <span className="vs-label">当前</span>
                      <span className="vs-value accent">
                        {v.currency} {latest.price?.toLocaleString()}
                      </span>
                    </div>
                    <div className="vs-item">
                      <span className="vs-label">最低</span>
                      <span className="vs-value">{min?.toLocaleString()}</span>
                    </div>
                    <div className="vs-item">
                      <span className="vs-label">最高</span>
                      <span className="vs-value">{max?.toLocaleString()}</span>
                    </div>
                    <div className="vs-item">
                      <span className="vs-label">记录</span>
                      <span className="vs-value">{points.length}条</span>
                    </div>
                  </div>
                ) : (
                  <p className="no-data-text">暂无价格数据</p>
                )}
                {/* Source URL */}
                {v.url && (
                  <a
                    href={v.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="variant-source-link"
                    onClick={e => e.stopPropagation()}
                  >
                    🔗 查看来源 →
                  </a>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Time Range Filter */}
      {variants.length > 0 && (
        <div className="days-filter">
          {[7, 14, 30, 90].map(d => (
            <button
              key={d}
              className={days === d ? 'active' : ''}
              onClick={() => setDays(d)}
            >
              {d}天
            </button>
          ))}
        </div>
      )}

      {/* Chart —— 每条线 = 一个 variant */}
      {chartData.length > 0 && (
        <div className="chart-container">
          <ResponsiveContainer width="100%" height={400}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e8dccf" />
              <XAxis dataKey="date" stroke="#8a7e6e" tick={{ fontSize: 11 }} />
              <YAxis stroke="#8a7e6e" tick={{ fontSize: 11 }} />
              <Tooltip
                contentStyle={{
                  background: '#fff',
                  border: '1px solid #e8dccf',
                  borderRadius: 8,
                }}
                labelStyle={{ color: '#3d3226' }}
              />
              <Legend />
              {variants.map((v, i) => (
                <Line
                  key={`${v.source_slug}__${v.box_size}`}
                  type="monotone"
                  dataKey={variantLabel(v)}
                  stroke={COLORS[i % COLORS.length]}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

function buildChartData(variants) {
  const dateMap = {};
  variants.forEach(v => {
    const label = variantLabel(v);
    (v.points || []).forEach(p => {
      const date = p.date?.split('T')[0] || p.date;
      if (!dateMap[date]) dateMap[date] = { date };
      dateMap[date][label] = p.price;
    });
  });
  return Object.values(dateMap).sort((a, b) => a.date.localeCompare(b.date));
}
