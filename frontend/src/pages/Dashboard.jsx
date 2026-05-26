import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchLatestPrices, fetchSources } from '../api';

const BRANDS_ORDER = [
  '高希霸', '蒙特', '罗密欧与朱丽叶', '帕特加斯',
  '好友', '乌普曼',
];

const SOURCE_URLS = {
  coh: 'https://cigarsofhabanos.com',
  ihavanas: 'https://ihavanas.com',
  egm: 'https://egmcigars.com',
};

export default function Dashboard() {
  const [snapshots, setSnapshots] = useState([]);
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeBrand, setActiveBrand] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    Promise.all([fetchSources(), fetchLatestPrices()])
      .then(([srcData, snapData]) => {
        setSources(srcData.results || srcData);
        setSnapshots(snapData.results || snapData);
        setLoading(false);
      })
      .catch(err => {
        console.error('价格数据加载失败', err);
        setError('数据加载失败，请刷新重试');
        setLoading(false);
      });
  }, []);

  const grouped = useMemo(() => {
    const map = {};
    snapshots.forEach(s => {
      const cigarId = s.cigar;
      const brandCn = s.cigar_brand_cn || s.cigar_brand;
      const key = `${brandCn}|||${cigarId}`;
      if (!map[key]) {
        map[key] = {
          cigar_id: cigarId,
          brand: brandCn,
          name: s.cigar_name,
          name_en: s.cigar_english_name,
          prices: [],
        };
      }
      map[key].prices.push(s);
    });
    let list = Object.values(map);
    list.sort((a, b) => {
      const ai = BRANDS_ORDER.indexOf(a.brand);
      const bi = BRANDS_ORDER.indexOf(b.brand);
      if (ai !== -1 && bi !== -1) return ai - bi;
      if (ai !== -1) return -1;
      if (bi !== -1) return 1;
      return a.brand.localeCompare(b.brand, 'zh');
    });
    return list;
  }, [snapshots]);

  const brands = useMemo(() => [...new Set(grouped.map(g => g.brand))], [grouped]);
  const filtered = useMemo(() => {
    return grouped.filter(g => !activeBrand || g.brand === activeBrand);
  }, [grouped, activeBrand]);

  const sourceSlugs = useMemo(() => {
    const slugs = new Set();
    snapshots.forEach(s => { if (s.source_slug) slugs.add(s.source_slug); });
    return [...slugs];
  }, [snapshots]);

  if (loading) {
    return (
      <div className="loading-state">
        <div className="spinner" />
        <p>加载价格数据…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="error-state">
        <div className="error-icon">⚠</div>
        <p>{error}</p>
        <button onClick={() => window.location.reload()}>重新加载</button>
      </div>
    );
  }

  if (filtered.length === 0) {
    return (
      <div className="empty-state">
        <div className="empty-icon">📭</div>
        <h3>暂无价格数据</h3>
        <p>等待价格数据抓取完成后自动显示</p>
      </div>
    );
  }

  return (
    <div className="dashboard">
      {/* Stats Bar */}
      <div className="stats-bar">
        <div className="stat-item">
          <span className="stat-value">{snapshots.length}</span>
          <span className="stat-label">价格条目</span>
        </div>
        <div className="stat-item">
          <span className="stat-value">{new Set(snapshots.map(s => s.cigar)).size}</span>
          <span className="stat-label">雪茄款式</span>
        </div>
        <div className="stat-item">
          <span className="stat-value">{brands.length}</span>
          <span className="stat-label">品牌覆盖</span>
        </div>
        <div className="stat-item">
          <span className="stat-value">{sourceSlugs.length}</span>
          <span className="stat-label">价格来源</span>
        </div>
      </div>

      {/* Brand Tabs */}
      <div className="brand-tabs">
        <button className={!activeBrand ? 'active' : ''} onClick={() => setActiveBrand('')}>
          全部品牌
        </button>
        {brands.map(b => (
          <button key={b} className={activeBrand === b ? 'active' : ''} onClick={() => setActiveBrand(b)}>
            {b}
          </button>
        ))}
      </div>

      {/* Price Cards Grid */}
      <div className="price-grid">
        {filtered.map(cigar => (
          <div
            key={cigar.cigar_id}
            className="price-card"
            onClick={() => navigate(`/cigar/${cigar.cigar_id}`)}
          >
            <div className="card-header">
              <span className="card-brand">{cigar.brand}</span>
            </div>
            <div className="card-body">
              <h3 className="card-name">{cigar.name}</h3>
              {cigar.name_en && cigar.name_en !== cigar.name && (
                <p className="card-name-en">{cigar.name_en}</p>
              )}
              <div className="card-prices">
                {cigar.prices.map((snap, i) => (
                  <div key={i} className="card-price-row">
                    <span className="source-tag">{snap.source_slug?.toUpperCase()}</span>
                    <span className="box-tag">
                      {snap.box_size != null ? `${snap.box_size}支` : '25支'}
                    </span>
                    {snap.in_stock ? (
                      <span className="price-value">
                        {snap.currency === 'USD' ? '$' : ''}
                        {snap.price.toLocaleString()}
                      </span>
                    ) : (
                      <span className="out-stock">缺货</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
