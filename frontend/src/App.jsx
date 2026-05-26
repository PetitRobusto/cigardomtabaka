import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import CigarDetail from './pages/CigarDetail';
import Alerts from './pages/Alerts';
import './index.css';

export default function App() {
  return (
    <BrowserRouter basename="/prices">
      <div className="app">
        <header className="app-header">
          <h1>📊 市场价格监控</h1>
          <nav>
            <NavLink to="/" end>仪表盘</NavLink>
            <NavLink to="/alerts">预警管理</NavLink>
          </nav>
        </header>
        <main>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/cigar/:id" element={<CigarDetail />} />
            <Route path="/alerts" element={<Alerts />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
