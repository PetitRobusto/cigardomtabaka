import { useEffect, useState } from 'react';
import { brandLogoUrl } from '../../utils/brandAssets';

interface BrandLoaderProps {
  fullScreen?: boolean;
  text?: string;
}

export function BrandLoader({
  fullScreen = false,
  text = '正在准备你的雪茄世界',
}: BrandLoaderProps) {
  const [slowText, setSlowText] = useState<string | null>(null);
  const status = slowText === text ? '加载时间较长，请稍候' : text;

  useEffect(() => {
    const slowTimer = window.setTimeout(() => {
      setSlowText(text);
    }, 10_000);

    return () => window.clearTimeout(slowTimer);
  }, [text]);

  return (
    <section
      className={`cdt-loader${fullScreen ? ' cdt-loader--screen' : ''}`}
      aria-busy="true"
    >
      <div className="cdt-loader__stage">
        <div className="cdt-loader__seal" aria-hidden="true">
          <svg className="cdt-loader__smoke" viewBox="0 0 115 94">
            <path className="cdt-loader__smoke-one" d="M35 90 C22 74, 52 66, 35 51 C20 37, 48 29, 42 8" />
            <path className="cdt-loader__smoke-two" d="M67 88 C81 72, 53 65, 70 49 C86 34, 57 25, 68 3" />
          </svg>
          <img className="cdt-loader__logo cdt-loader__logo--ghost" src={brandLogoUrl} alt="" />
          <img className="cdt-loader__logo cdt-loader__logo--ink" src={brandLogoUrl} alt="" />
          <img className="cdt-loader__logo cdt-loader__logo--glint" src={brandLogoUrl} alt="" />
          <span className="cdt-loader__needle" />
        </div>
        <div className="cdt-loader__caption" aria-hidden="true">CigarDomTabaka</div>
        <p className="cdt-loader__status" role="status" aria-live="polite">{status}</p>
        <div className="cdt-loader__progress" aria-hidden="true" />
        {slowText === text && (
          <button className="cdt-loader__retry cdt-loader__retry--visible" type="button" onClick={() => window.location.reload()}>
            重新加载
          </button>
        )}
      </div>
    </section>
  );
}
