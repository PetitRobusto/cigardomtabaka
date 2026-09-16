import { useEffect, useState } from 'react';
import { brandMotionLogoUrl, habanosSpecialistLogoUrl } from '../../utils/brandAssets';

interface BrandLoaderProps {
  fullScreen?: boolean;
  text?: string;
}

export function BrandLoader({
  fullScreen = false,
  text = '莫斯科持证雪茄服务商',
}: BrandLoaderProps) {
  const [logoReady, setLogoReady] = useState(false);
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
        <img
          className={`cdt-loader__motion-logo${logoReady ? ' cdt-loader__motion-logo--ready' : ''}`}
          src={brandMotionLogoUrl}
          alt=""
          width="640"
          height="525"
          aria-hidden="true"
          onLoad={() => setLogoReady(true)}
        />
        <div className="cdt-loader__status" role="status" aria-live="polite">
          <img
            className="cdt-loader__specialist"
            src={habanosSpecialistLogoUrl}
            alt="Habanos Specialist"
            width="173"
            height="216"
          />
          <span className="cdt-loader__status-copy">
            <span>{status}</span>
            <span className="cdt-loading-dots" aria-hidden="true"><i /><i /><i /></span>
          </span>
        </div>
        {slowText === text && (
          <button className="cdt-loader__retry cdt-loader__retry--visible" type="button" onClick={() => window.location.reload()}>
            重新加载
          </button>
        )}
      </div>
    </section>
  );
}
