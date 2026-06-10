import axios from 'axios';
import * as cheerio from 'cheerio';
import { PrismaClient } from '@prisma/client';
import { logger } from '../index';

const prisma = new PrismaClient();

export interface ScrapeTarget {
  municipalityCode: string;
  name: string;
  url: string;
  selectors: {
    title: string;
    description: string;
    amount?: string;
    deadline?: string;
  };
}

export const scrapeTargets: ScrapeTarget[] = [
  {
    municipalityCode: '011002',
    name: '札幌市',
    url: 'https://www.city.sapporo.jp/keizai/shien/hojo/',
    selectors: { title: 'h2.title, .news-title', description: '.description, .content p', amount: '.amount', deadline: '.deadline' },
  },
  {
    municipalityCode: '041009',
    name: '仙台市',
    url: 'https://www.city.sendai.jp/keizai/hojo/',
    selectors: { title: 'h2, .entry-title', description: '.entry-content p', amount: '.hojo-amount', deadline: '.application-period' },
  },
  {
    municipalityCode: '110001',
    name: 'さいたま市',
    url: 'https://www.city.saitama.lg.jp/006/014/006/index.html',
    selectors: { title: '.news h3, h2', description: '.news-body p', amount: '.amount-info', deadline: '.period' },
  },
  {
    municipalityCode: '121002',
    name: '千葉市',
    url: 'https://www.city.chiba.jp/keizai/hojo/',
    selectors: { title: 'h2.section-title', description: '.section-body', amount: '.hojo-kingaku', deadline: '.boshu-kikan' },
  },
  {
    municipalityCode: '141003',
    name: '横浜市',
    url: 'https://www.city.yokohama.lg.jp/business/kigyoshien/hojo/',
    selectors: { title: '.info-title', description: '.info-body', amount: '.max-amount', deadline: '.apply-period' },
  },
  {
    municipalityCode: '142011',
    name: '川崎市',
    url: 'https://www.city.kawasaki.jp/280/hojo/',
    selectors: { title: 'h3.list-title', description: '.list-desc', amount: '.subsidy-amount', deadline: '.subsidy-period' },
  },
  {
    municipalityCode: '142029',
    name: '相模原市',
    url: 'https://www.city.sagamihara.kanagawa.jp/business/hojo/',
    selectors: { title: 'h2, .news-title', description: '.news-body', amount: '.kingaku', deadline: '.kikan' },
  },
  {
    municipalityCode: '151009',
    name: '新潟市',
    url: 'https://www.city.niigata.lg.jp/business/hojo/',
    selectors: { title: '.list-title h3', description: '.list-body p', amount: '.jyosei-kingaku', deadline: '.boshu-kikan' },
  },
  {
    municipalityCode: '221007',
    name: '静岡市',
    url: 'https://www.city.shizuoka.lg.jp/keizai/hojo/',
    selectors: { title: 'h2.news-title', description: '.news-content', amount: '.subsidy-max', deadline: '.apply-end' },
  },
  {
    municipalityCode: '222003',
    name: '浜松市',
    url: 'https://www.city.hamamatsu.shizuoka.jp/sangyou/hojo/',
    selectors: { title: '.entry-title', description: '.entry-body', amount: '.hojo-gaku', deadline: '.boshu-kikan' },
  },
  {
    municipalityCode: '231002',
    name: '名古屋市',
    url: 'https://www.city.nagoya.jp/keizai/hojo/',
    selectors: { title: '.news-title h3', description: '.news-body', amount: '.hojo-amount', deadline: '.hojo-period' },
  },
  {
    municipalityCode: '261009',
    name: '京都市',
    url: 'https://www.city.kyoto.lg.jp/sankan/hojo/',
    selectors: { title: 'h2.section-header', description: '.section-content p', amount: '.max-hojo', deadline: '.apply-deadline' },
  },
  {
    municipalityCode: '271004',
    name: '大阪市',
    url: 'https://www.city.osaka.lg.jp/keizaisenryaku/hojo/',
    selectors: { title: 'h3.news-heading', description: '.news-text', amount: '.hojo-gaku', deadline: '.boshu-kigen' },
  },
  {
    municipalityCode: '272019',
    name: '堺市',
    url: 'https://www.city.sakai.lg.jp/sangyo/hojo/',
    selectors: { title: 'h2.list-title', description: '.list-body', amount: '.kingaku', deadline: '.kigen' },
  },
  {
    municipalityCode: '281004',
    name: '神戸市',
    url: 'https://www.city.kobe.lg.jp/a23382/hojo/',
    selectors: { title: '.news-title', description: '.news-body p', amount: '.hojo-max', deadline: '.hojo-period' },
  },
  {
    municipalityCode: '331007',
    name: '岡山市',
    url: 'https://www.city.okayama.jp/keizai/hojo/',
    selectors: { title: 'h2.entry-title', description: '.entry-content', amount: '.jyosei-max', deadline: '.apply-kigen' },
  },
  {
    municipalityCode: '341002',
    name: '広島市',
    url: 'https://www.city.hiroshima.lg.jp/site/hojo/',
    selectors: { title: '.info-title h3', description: '.info-content', amount: '.hojo-gaku', deadline: '.boshu-end' },
  },
  {
    municipalityCode: '401005',
    name: '福岡市',
    url: 'https://www.city.fukuoka.lg.jp/keizai/hojo/',
    selectors: { title: 'h2.news-title', description: '.news-detail p', amount: '.max-hojo-gaku', deadline: '.apply-period' },
  },
  {
    municipalityCode: '431004',
    name: '熊本市',
    url: 'https://www.city.kumamoto.jp/hojo/index.html',
    selectors: { title: '.article-title', description: '.article-body', amount: '.hojo-amount', deadline: '.kigen-date' },
  },
  {
    municipalityCode: '402012',
    name: '北九州市',
    url: 'https://www.city.kitakyushu.lg.jp/keizai/hojo/',
    selectors: { title: '.page-title', description: '.page-body p', amount: '.max-amount', deadline: '.deadline' },
  },
  // 東京23区
  {
    municipalityCode: '131016',
    name: '千代田区',
    url: 'https://www.city.chiyoda.lg.jp/koho/machidukuri/sangyo/hojo/',
    selectors: { title: 'h3.section-title', description: '.section-body', amount: '.hojo-gaku', deadline: '.apply-kigen' },
  },
  {
    municipalityCode: '131024',
    name: '中央区',
    url: 'https://www.city.chuo.lg.jp/a0048/index.html',
    selectors: { title: '.news-title', description: '.news-content', amount: '.kingaku', deadline: '.period' },
  },
  {
    municipalityCode: '131032',
    name: '港区',
    url: 'https://www.city.minato.tokyo.jp/sangyoshinko/hojo/',
    selectors: { title: 'h2.content-title', description: '.content-body', amount: '.subsidy-amount', deadline: '.boshu-kikan' },
  },
  {
    municipalityCode: '131041',
    name: '新宿区',
    url: 'https://www.city.shinjuku.lg.jp/sangyo/hojo/',
    selectors: { title: '.news-heading', description: '.news-text', amount: '.hojo-max', deadline: '.apply-end' },
  },
  {
    municipalityCode: '131059',
    name: '文京区',
    url: 'https://www.city.bunkyo.lg.jp/sangyo/hojo/',
    selectors: { title: 'h3.article-title', description: '.article-body p', amount: '.kingaku-info', deadline: '.kigen-info' },
  },
  {
    municipalityCode: '131067',
    name: '台東区',
    url: 'https://www.city.taito.lg.jp/sangyo/hojo/',
    selectors: { title: '.list-title', description: '.list-body', amount: '.hojo-gaku', deadline: '.boshu-kigen' },
  },
  {
    municipalityCode: '131075',
    name: '墨田区',
    url: 'https://www.city.sumida.lg.jp/sangyo/hojo/',
    selectors: { title: 'h2.page-title', description: '.page-content', amount: '.jyosei-gaku', deadline: '.apply-period' },
  },
  {
    municipalityCode: '131083',
    name: '江東区',
    url: 'https://www.city.koto.lg.jp/sangyo/hojo/',
    selectors: { title: '.section-heading', description: '.section-content', amount: '.max-amount', deadline: '.deadline' },
  },
  {
    municipalityCode: '131091',
    name: '品川区',
    url: 'https://www.city.shinagawa.tokyo.jp/sangyo/hojo/',
    selectors: { title: 'h3.news-title', description: '.news-body', amount: '.hojo-gaku', deadline: '.boshu-kikan' },
  },
  {
    municipalityCode: '131105',
    name: '目黒区',
    url: 'https://www.city.meguro.tokyo.jp/sangyo/hojo/',
    selectors: { title: '.article-heading', description: '.article-content p', amount: '.kingaku', deadline: '.kigen' },
  },
  // More cities
  {
    municipalityCode: '012041',
    name: '旭川市',
    url: 'https://www.city.asahikawa.hokkaido.jp/sangyo/hojo/',
    selectors: { title: 'h2.news-title', description: '.news-detail', amount: '.hojo-amount', deadline: '.apply-deadline' },
  },
  {
    municipalityCode: '052019',
    name: '秋田市',
    url: 'https://www.city.akita.lg.jp/sangyo/hojo/',
    selectors: { title: '.entry-title', description: '.entry-body p', amount: '.max-hojo', deadline: '.boshu-kigan' },
  },
  {
    municipalityCode: '062014',
    name: '山形市',
    url: 'https://www.city.yamagata-yamagata.lg.jp/sangyo/hojo/',
    selectors: { title: 'h2.section-title', description: '.section-body', amount: '.hojo-gaku', deadline: '.boshu-kikan' },
  },
  {
    municipalityCode: '072039',
    name: '郡山市',
    url: 'https://www.city.koriyama.lg.jp/sangyo/hojo/',
    selectors: { title: '.news-title h3', description: '.news-body', amount: '.kingaku', deadline: '.kigen' },
  },
  {
    municipalityCode: '082015',
    name: '水戸市',
    url: 'https://www.city.mito.lg.jp/sangyo/hojo/',
    selectors: { title: 'h2.list-heading', description: '.list-content', amount: '.hojo-max', deadline: '.apply-period' },
  },
  {
    municipalityCode: '092011',
    name: '宇都宮市',
    url: 'https://www.city.utsunomiya.tochigi.jp/sangyo/hojo/',
    selectors: { title: '.page-title', description: '.page-body', amount: '.jyosei-kingaku', deadline: '.apply-kigen' },
  },
  {
    municipalityCode: '102016',
    name: '前橋市',
    url: 'https://www.city.maebashi.gunma.jp/sangyo/hojo/',
    selectors: { title: 'h3.info-title', description: '.info-body', amount: '.hojo-gaku', deadline: '.boshu-kikan' },
  },
  {
    municipalityCode: '102024',
    name: '高崎市',
    url: 'https://www.city.takasaki.gunma.jp/sangyo/hojo/',
    selectors: { title: '.news-title', description: '.news-content p', amount: '.amount', deadline: '.deadline' },
  },
  {
    municipalityCode: '112037',
    name: '川口市',
    url: 'https://www.city.kawaguchi.lg.jp/sangyo/hojo/',
    selectors: { title: 'h2.section-heading', description: '.section-text', amount: '.max-hojo', deadline: '.apply-end' },
  },
  {
    municipalityCode: '122041',
    name: '船橋市',
    url: 'https://www.city.funabashi.lg.jp/sangyo/hojo/',
    selectors: { title: '.article-title', description: '.article-body', amount: '.kingaku-info', deadline: '.kigen-info' },
  },
];

export async function scrapeSubsidies(target: ScrapeTarget): Promise<void> {
  try {
    const response = await axios.get(target.url, {
      timeout: 10000,
      headers: {
        'User-Agent': 'SubsidyNavigator/1.0 (Research Bot; contact@subsidy-navigator.jp)',
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'ja,en-US;q=0.9',
      },
    });

    const $ = cheerio.load(response.data);
    const municipality = await prisma.municipality.findUnique({
      where: { code: target.municipalityCode },
    });

    if (!municipality) {
      logger.warn(`Municipality not found: ${target.municipalityCode} (${target.name})`);
      return;
    }

    const titleElements = $(target.selectors.title);
    const descElements = $(target.selectors.description);

    const count = Math.min(titleElements.length, descElements.length, 5);

    for (let i = 0; i < count; i++) {
      const title = $(titleElements[i]).text().trim();
      const description = $(descElements[i]).text().trim();

      if (!title || title.length < 5) continue;

      let maxAmount: number | null = null;
      if (target.selectors.amount) {
        const amountText = $(target.selectors.amount).first().text();
        const amountMatch = amountText.match(/(\d+(?:,\d{3})*)/);
        if (amountMatch) {
          maxAmount = parseInt(amountMatch[1].replace(/,/g, ''), 10);
        }
      }

      let applicationPeriodEnd: Date | null = null;
      if (target.selectors.deadline) {
        const deadlineText = $(target.selectors.deadline).first().text();
        const dateMatch = deadlineText.match(/(\d{4})[年/](\d{1,2})[月/](\d{1,2})/);
        if (dateMatch) {
          applicationPeriodEnd = new Date(
            parseInt(dateMatch[1], 10),
            parseInt(dateMatch[2], 10) - 1,
            parseInt(dateMatch[3], 10)
          );
        }
      }

      const category = detectCategory(title + ' ' + description);

      await prisma.subsidy.upsert({
        where: {
          id: `scraped-${target.municipalityCode}-${Buffer.from(title).toString('base64').substring(0, 20)}`,
        },
        update: {
          description: description || '詳細は自治体ウェブサイトをご確認ください。',
          maxAmount,
          applicationPeriodEnd,
          scrapedAt: new Date(),
          status: applicationPeriodEnd && applicationPeriodEnd < new Date() ? 'CLOSED' : 'OPEN',
        },
        create: {
          id: `scraped-${target.municipalityCode}-${Buffer.from(title).toString('base64').substring(0, 20)}`,
          title,
          description: description || '詳細は自治体ウェブサイトをご確認ください。',
          category,
          maxAmount,
          applicationPeriodEnd,
          scrapeUrl: target.url,
          scrapedAt: new Date(),
          status: 'OPEN',
          municipalityId: municipality.id,
        },
      });
    }

    logger.info(`Scraped ${count} subsidies from ${target.name}`);
  } catch (error) {
    if (axios.isAxiosError(error)) {
      if (error.code === 'ECONNREFUSED' || error.code === 'ENOTFOUND' || error.response?.status === 404) {
        logger.warn(`Skipping ${target.name}: ${error.code || error.response?.status}`);
      } else {
        logger.error(`Error scraping ${target.name}: ${error.message}`);
      }
    } else {
      logger.error(`Unexpected error scraping ${target.name}:`, error);
    }
  }
}

function detectCategory(text: string): string {
  const lower = text.toLowerCase();
  if (lower.includes('it') || lower.includes('デジタル') || lower.includes('dx') || lower.includes('ict')) {
    return 'IT導入';
  }
  if (lower.includes('設備') || lower.includes('機械') || lower.includes('ものづくり')) {
    return '設備投資';
  }
  if (lower.includes('雇用') || lower.includes('採用') || lower.includes('人材')) {
    return '雇用促進';
  }
  if (lower.includes('環境') || lower.includes('省エネ') || lower.includes('再生可能') || lower.includes('太陽光')) {
    return '環境・エネルギー';
  }
  if (lower.includes('創業') || lower.includes('起業') || lower.includes('開業')) {
    return '創業支援';
  }
  if (lower.includes('販路') || lower.includes('海外') || lower.includes('輸出') || lower.includes('展示会')) {
    return '販路拡大';
  }
  return 'その他';
}

export async function runFullScrape(): Promise<void> {
  logger.info(`Starting full scrape of ${scrapeTargets.length} targets`);

  for (const target of scrapeTargets) {
    await scrapeSubsidies(target);
    // Small delay between requests to be respectful
    await new Promise(resolve => setTimeout(resolve, 1000));
  }

  logger.info('Full scrape completed');
}
