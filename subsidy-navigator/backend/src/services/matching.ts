import { PrismaClient, Subsidy, Municipality, SubsidyStatus } from '@prisma/client';

const prisma = new PrismaClient();

export interface MatchingInput {
  email: string;
  company: string;
  prefecture: string;
  employeeCount?: number;
  industry?: string;
  annualRevenue?: number;
  needs: string[];
}

export interface MatchResult {
  subsidy: Subsidy & { municipality: Municipality };
  score: number;
  matchReasons: string[];
}

const CATEGORY_NEEDS_MAP: Record<string, string[]> = {
  'IT導入': ['IT・デジタル化', 'DX推進', 'テレワーク', 'ECサイト構築', 'AI活用'],
  '設備投資': ['設備・機械購入', '生産性向上', '工場・施設改善', '農業近代化'],
  '雇用促進': ['採用・雇用', '人材育成', '正社員化', '障がい者雇用'],
  '環境・エネルギー': ['省エネ', '再生可能エネルギー', '脱炭素', 'SDGs'],
  '創業支援': ['創業・起業', '新事業展開', '第二創業'],
  '販路拡大': ['販路拡大', '海外展開', 'マーケティング', '展示会出展', 'EC・越境'],
};

const INDUSTRY_CATEGORY_MAP: Record<string, string[]> = {
  '製造業': ['設備投資', 'IT導入', '環境・エネルギー'],
  'IT・情報通信': ['IT導入', '販路拡大', '創業支援'],
  '小売業': ['IT導入', '販路拡大', '創業支援'],
  '飲食業': ['IT導入', '創業支援', '販路拡大'],
  '建設業': ['設備投資', '雇用促進', '環境・エネルギー'],
  '農林水産業': ['設備投資', '環境・エネルギー', '販路拡大'],
  '医療・福祉': ['IT導入', '雇用促進', '設備投資'],
  '観光・宿泊': ['IT導入', '販路拡大', '設備投資'],
  'サービス業': ['IT導入', '販路拡大', '創業支援'],
  '卸売業': ['IT導入', '販路拡大', '設備投資'],
};

export async function matchSubsidies(profile: MatchingInput): Promise<MatchResult[]> {
  // Fetch all open subsidies with municipality
  const allSubsidies = await prisma.subsidy.findMany({
    where: { status: SubsidyStatus.OPEN },
    include: { municipality: true },
    take: 200,
  });

  const results: MatchResult[] = [];

  for (const subsidy of allSubsidies) {
    const { score, reasons } = scoreSubsidy(subsidy, profile);

    if (score > 0) {
      results.push({
        subsidy,
        score,
        matchReasons: reasons,
      });
    }
  }

  // Sort by score descending
  return results
    .sort((a, b) => b.score - a.score)
    .slice(0, 30);
}

function scoreSubsidy(
  subsidy: Subsidy & { municipality: Municipality },
  profile: MatchingInput
): { score: number; reasons: string[] } {
  let score = 0;
  const reasons: string[] = [];

  // Prefecture match (strong signal)
  if (subsidy.municipality.prefecture === profile.prefecture) {
    score += 40;
    reasons.push(`${profile.prefecture}の補助金`);
  }

  // National/cross-prefecture subsidies (no prefecture penalty)
  if (subsidy.municipality.name.includes('東京')) {
    score += 10; // National programs often in Tokyo
  }

  // Category match from needs
  for (const need of profile.needs) {
    for (const [category, needKeywords] of Object.entries(CATEGORY_NEEDS_MAP)) {
      if (needKeywords.some(kw => need.includes(kw) || kw.includes(need))) {
        if (subsidy.category === category) {
          score += 30;
          reasons.push(`${need}に対応`);
          break;
        }
      }
    }
  }

  // Industry alignment
  if (profile.industry) {
    const preferredCategories = INDUSTRY_CATEGORY_MAP[profile.industry] || [];
    if (preferredCategories.includes(subsidy.category)) {
      score += 20;
      reasons.push(`${profile.industry}向け`);
    }
  }

  // Employee count-based scoring
  if (profile.employeeCount !== undefined) {
    const targetText = (subsidy.targetBusiness || '').toLowerCase();
    if (profile.employeeCount <= 5 && targetText.includes('小規模')) {
      score += 15;
      reasons.push('小規模事業者対象');
    } else if (profile.employeeCount <= 300 && (targetText.includes('中小企業') || targetText.includes('中小'))) {
      score += 10;
      reasons.push('中小企業対象');
    }
  }

  // Revenue-based scoring
  if (profile.annualRevenue !== undefined) {
    if (profile.annualRevenue < 50000000 && subsidy.category === '創業支援') {
      score += 10;
      reasons.push('売上規模が合致');
    }
  }

  // Amount bonus for larger subsidies
  if (subsidy.maxAmount && subsidy.maxAmount >= 5000000) {
    score += 5;
    reasons.push(`最大${Math.floor(subsidy.maxAmount / 10000)}万円`);
  }

  // Recency bonus
  const daysSinceCreated = (Date.now() - new Date(subsidy.createdAt).getTime()) / (1000 * 60 * 60 * 24);
  if (daysSinceCreated <= 30) {
    score += 5;
    reasons.push('新着情報');
  }

  // Deadline urgency (closer = higher relevance)
  if (subsidy.applicationPeriodEnd) {
    const daysUntilDeadline = (new Date(subsidy.applicationPeriodEnd).getTime() - Date.now()) / (1000 * 60 * 60 * 24);
    if (daysUntilDeadline > 0 && daysUntilDeadline <= 30) {
      score += 8;
      reasons.push(`締切まで約${Math.round(daysUntilDeadline)}日`);
    } else if (daysUntilDeadline > 30 && daysUntilDeadline <= 90) {
      score += 4;
    }
  }

  // De-duplicate reasons
  const uniqueReasons = [...new Set(reasons)];

  return { score, reasons: uniqueReasons };
}
