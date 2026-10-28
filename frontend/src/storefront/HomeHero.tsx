import type { StoreHeroLinks, StoreLocale } from "./types";
import { homeHeroImageSizes, homeHeroImageSrcSet } from "./HomeHero.images";
import "./HomeHero.css";
import "./HomeHero.outlines.css";

type HomeHeroProps = {
  locale: StoreLocale;
  catalogUrl: string;
  stockUrl: string;
  links?: StoreHeroLinks;
};

const heroCopy: Record<StoreLocale, {
  kicker: string;
  title: string;
  titleAccent: string;
  lead: string;
  facts: string[];
  contact: string;
  browseStock: string;
  stageLabel: string;
}> = {
  zh: {
    kicker: "莫斯科古巴雪茄专业服务商",
    title: "在莫斯科，",
    titleAccent: "探索古巴雪茄的魅力",
    lead: "CigarDomTabaka位于莫斯科市西南区的加加林区，超过50种古巴雪茄，Habanos Point认证门店，从高希霸Behike、高希霸世纪 6 号到千里达创建，探索古巴雪茄的经典与限量系列，专业茄房储存，正品平价销售。",
    facts: ["正品保证", "平价销售", "专业茄房", "莫斯科门店"],
    contact: "联系门店",
    browseStock: "浏览现货",
    stageLabel: "雪茄陈列",
  },
  en: {
    kicker: "Cuban cigars in Moscow",
    title: "In Moscow, discover the charm of",
    titleAccent: "Cuban cigars",
    lead: "Located in the Gagarinsky District of southwest Moscow, CigarDomTabaka is a Habanos Point certified shop offering over 50 Cuban cigars. From Cohiba Behike and Cohiba Siglo VI to Trinidad Fundadores, explore classic and limited releases, stored in a professional humidor and sold at fair prices with authenticity guaranteed.",
    facts: ["Authenticity guaranteed", "Fair prices", "Professional humidor", "Moscow shop"],
    contact: "Contact the shop",
    browseStock: "Browse in-stock cigars",
    stageLabel: "Cigar display",
  },
  ru: {
    kicker: "Специалисты по кубинским сигарам в Москве",
    title: "Откройте для себя в Москве",
    titleAccent: "очарование кубинских сигар",
    lead: "CigarDomTabaka находится в Гагаринском районе на юго-западе Москвы. В сертифицированном магазине Habanos Point представлено более 50 кубинских сигар — от Cohiba Behike и Cohiba Siglo VI до Trinidad Fundadores. Откройте для себя классические и лимитированные серии: профессиональное хранение в хьюмидоре, гарантия подлинности и доступные цены.",
    facts: ["Гарантия подлинности", "Доступные цены", "Профессиональный хьюмидор", "Магазин в Москве"],
    contact: "Связаться с магазином",
    browseStock: "Сигары в наличии",
    stageLabel: "Витрина сигар",
  },
};

const cigars = [
  {
    className: "bhk56",
    name: "Cohiba BHK 56",
    stem: "cohiba-bhk-56",
    maxWidth: 997,
    width: 997,
    height: 139,
  },
  {
    className: "siglo",
    name: "Cohiba Siglo VI",
    stem: "cohiba-siglo-vi",
    maxWidth: 999,
    width: 999,
    height: 145,
  },
  {
    className: "casilda",
    name: "Trinidad Casilda · Colección Habanos",
    stem: "trinidad-casilda",
    maxWidth: 998,
    width: 998,
    height: 119,
  },
  {
    className: "bhk52",
    name: "Cohiba BHK 52",
    stem: "cohiba-bhk-52",
    maxWidth: 996,
    width: 996,
    height: 171,
  },
  {
    className: "ingenios",
    name: "Trinidad Ingenios · Edición Limitada",
    stem: "trinidad-ingenios",
    maxWidth: 999,
    width: 999,
    height: 101,
  },
] as const;

export function HomeHero({ locale, catalogUrl, stockUrl, links }: HomeHeroProps) {
  const copy = heroCopy[locale];

  return (
    <section className="store-home-hero" aria-labelledby="store-home-hero-title">
      <div className="store-home-hero__inner">
        <div className="store-home-hero__copy">
          <p className="store-home-hero__kicker">{copy.kicker}</p>
          <div className="store-home-hero__rule" aria-hidden="true" />
          <h1 className="store-home-hero__title" id="store-home-hero-title">
            {copy.title}{locale === "zh" ? "" : " "}<em>{copy.titleAccent}</em>
          </h1>
          <p className="store-home-hero__lead">{copy.lead}</p>
          <ul className="store-home-hero__facts">
            {copy.facts.map((fact) => <li key={fact}>{fact}</li>)}
          </ul>
          <div className="store-home-hero__actions">
            <a className="store-home-hero__primary" href="#store-contact">{copy.contact}</a>
            <a className="store-home-hero__secondary" href={stockUrl}>{copy.browseStock} →</a>
          </div>
        </div>

        <div className="store-home-hero__stage" role="group" aria-label={copy.stageLabel}>
          {cigars.map((cigar, index) => (
            <figure className={`store-home-hero__cigar store-home-hero__cigar--${cigar.className}`} key={cigar.name}>
              <a href={links?.[cigar.className] || catalogUrl} aria-label={cigar.name}>
                <img
                  src={`/media/home-hero-v1/${cigar.stem}-640.webp`}
                  srcSet={homeHeroImageSrcSet(cigar.stem, cigar.maxWidth)}
                  sizes={homeHeroImageSizes[cigar.className]}
                  alt={`${cigar.name} — ${locale === "zh" ? "单支雪茄图片" : locale === "ru" ? "изображение одной сигары" : "single cigar image"}`}
                  width={cigar.width}
                  height={cigar.height}
                  loading={index === 0 ? "eager" : "lazy"}
                  fetchPriority={index === 0 ? "high" : "auto"}
                />
              </a>
              <span className="store-home-hero__number" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
            </figure>
          ))}
        </div>
      </div>
      <div className="store-home-hero__legend" aria-hidden="true">
        {cigars.map((cigar, index) => <span key={cigar.name}><b>{String(index + 1).padStart(2, "0")}</b>{cigar.name}</span>)}
      </div>
    </section>
  );
}
