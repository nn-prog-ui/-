import { PrismaClient } from '@prisma/client';
import bcrypt from 'bcryptjs';

const prisma = new PrismaClient();

const nationalSubsidies = [
  { title: 'IT導入補助金2024', description: 'ITツール導入を支援する補助金。中小企業・小規模事業者のデジタル化を促進。', category: 'IT・デジタル', targetType: '中小企業', level: '国', prefecture: '全国', maxAmount: 4500000n, subsidyRate: '最大3/4', status: 'active', applicationUrl: 'https://www.it-hojo.jp/' },
  { title: 'ものづくり・商業・サービス生産性向上促進補助金', description: '革新的な製品・サービス開発や生産プロセス改善を支援。', category: '設備投資', targetType: '中小企業', level: '国', prefecture: '全国', maxAmount: 12500000n, subsidyRate: '1/2〜2/3', status: 'active', applicationUrl: 'https://portal.monodukuri-hojo.jp/' },
  { title: '小規模事業者持続化補助金', description: '小規模事業者の販路開拓や生産性向上を支援。', category: '販路拡大', targetType: '小規模事業者', level: '国', prefecture: '全国', maxAmount: 2000000n, subsidyRate: '2/3', status: 'active', applicationUrl: 'https://jizokukahojokin.info/' },
  { title: '事業再構築補助金', description: 'ポストコロナ時代の経済社会の変化に対応するための事業再構築を支援。', category: '事業再構築', targetType: '中小企業', level: '国', prefecture: '全国', maxAmount: 150000000n, subsidyRate: '1/2〜2/3', status: 'active', applicationUrl: 'https://jigyou-saikouchiku.go.jp/' },
  { title: '雇用調整助成金', description: '経済上の理由により事業活動の縮小を余儀なくされた事業主への助成。', category: '雇用促進', targetType: '全事業者', level: '国', prefecture: '全国', maxAmount: 9000n, subsidyRate: '2/3〜4/5', status: 'active', applicationUrl: 'https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/koyou_roudou/koyou/kyufukin/pageL07.html' },
  { title: 'キャリアアップ助成金', description: '非正規労働者の正規雇用化・処遇改善を支援する助成金。', category: '雇用促進', targetType: '全事業者', level: '国', prefecture: '全国', maxAmount: 720000n, subsidyRate: '定額', status: 'active', applicationUrl: 'https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/koyou_roudou/part_haken/jigyounushi/career.html' },
  { title: '地方創生推進交付金', description: '地方公共団体の自主的・主体的な取り組みを支援する交付金。', category: '地方創生', targetType: '地方公共団体', level: '国', prefecture: '全国', maxAmount: 500000000n, subsidyRate: '1/2', status: 'active', applicationUrl: 'https://www.chisou.go.jp/tiiki/tiikisaisei/index.html' },
  { title: '省エネルギー投資促進に向けた支援補助金', description: '工場・事業場における省エネルギー設備への投資を支援。', category: '環境・エネルギー', targetType: '全事業者', level: '国', prefecture: '全国', maxAmount: 150000000n, subsidyRate: '1/3〜1/2', status: 'active', applicationUrl: 'https://sii.or.jp/shoene_invest/' },
  { title: 'J-クレジット制度', description: '省エネルギー設備導入や再生可能エネルギー利用によるCO2削減量をクレジットとして認証。', category: '環境・エネルギー', targetType: '全事業者', level: '国', prefecture: '全国', maxAmount: null, subsidyRate: '－', status: 'active', applicationUrl: 'https://japancredit.go.jp/' },
  { title: '創業促進補助金', description: '新たに創業する者に対して、創業に要する経費の一部を補助。', category: '創業支援', targetType: '創業者', level: '国', prefecture: '全国', maxAmount: 2000000n, subsidyRate: '2/3', status: 'active', applicationUrl: 'https://www.chusho.meti.go.jp/shogyo/shogyo/index.html' },
  { title: '中小企業デジタル化応援隊事業', description: 'ITの活用・デジタル化に取り組む中小企業等を専門家が支援。', category: 'IT・デジタル', targetType: '中小企業', level: '国', prefecture: '全国', maxAmount: 300000n, subsidyRate: '補助率あり', status: 'active', applicationUrl: 'https://digitalization-support.jp/' },
  { title: 'トライアル雇用助成金', description: '就職困難者をトライアル雇用として雇い入れた事業主への助成。', category: '雇用促進', targetType: '全事業者', level: '国', prefecture: '全国', maxAmount: 40000n, subsidyRate: '定額/月', status: 'active', applicationUrl: 'https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/koyou_roudou/koyou/kyufukin/trial_koyou.html' },
  { title: '農業次世代人材投資資金', description: '農業経営を担う次世代の担い手の確保・育成を支援。', category: '農業・林業', targetType: '農業従事者', level: '国', prefecture: '全国', maxAmount: 1500000n, subsidyRate: '定額', status: 'active', applicationUrl: 'https://www.maff.go.jp/j/new_farmer/new_approach/ninaite.html' },
  { title: 'ものづくり補助金（デジタル枠）', description: 'DX化やデジタル技術を活用した製品・サービス開発を支援。', category: 'IT・デジタル', targetType: '中小企業', level: '国', prefecture: '全国', maxAmount: 12500000n, subsidyRate: '2/3〜3/4', status: 'active', applicationUrl: 'https://portal.monodukuri-hojo.jp/' },
  { title: '輸出促進補助金', description: '中小企業の海外展開・輸出拡大を支援する補助金。', category: '海外展開', targetType: '中小企業', level: '国', prefecture: '全国', maxAmount: 5000000n, subsidyRate: '1/2', status: 'active', applicationUrl: 'https://www.jetro.go.jp/' },
  { title: 'BCP策定支援補助金', description: '中小企業の事業継続計画（BCP）策定を支援する補助金。', category: '経営支援', targetType: '中小企業', level: '国', prefecture: '全国', maxAmount: 2000000n, subsidyRate: '2/3', status: 'active', applicationUrl: 'https://www.chusho.meti.go.jp/' },
  { title: '働き方改革推進支援助成金', description: '労働時間の短縮・年次有給休暇取得促進に取り組む中小企業への助成。', category: '雇用促進', targetType: '中小企業', level: '国', prefecture: '全国', maxAmount: 1000000n, subsidyRate: '3/4', status: 'active', applicationUrl: 'https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000148322.html' },
  { title: '商店街活性化事業補助金', description: '商店街等が行う空き店舗解消や集客イベント等の活性化事業を支援。', category: '販路拡大', targetType: '商店街', level: '国', prefecture: '全国', maxAmount: 10000000n, subsidyRate: '2/3', status: 'active', applicationUrl: 'https://www.chusho.meti.go.jp/shogyo/shogyo/index.html' },
  { title: 'IoT推進ラボ支援補助金', description: 'IoT・AI等の先進技術を活用したプロジェクトの実証支援。', category: 'IT・デジタル', targetType: '全事業者', level: '国', prefecture: '全国', maxAmount: 30000000n, subsidyRate: '1/2', status: 'active', applicationUrl: 'https://www.meti.go.jp/' },
  { title: '再生可能エネルギー導入補助金', description: '太陽光・風力・地熱等の再生可能エネルギー設備導入を支援。', category: '環境・エネルギー', targetType: '全事業者', level: '国', prefecture: '全国', maxAmount: 100000000n, subsidyRate: '1/3〜1/2', status: 'active', applicationUrl: 'https://www.env.go.jp/' },
  { title: '障害者雇用促進助成金', description: '障害者を雇用する事業主の職場環境整備等を支援する助成金。', category: '雇用促進', targetType: '全事業者', level: '国', prefecture: '全国', maxAmount: 6000000n, subsidyRate: '3/4', status: 'active', applicationUrl: 'https://www.jeed.go.jp/' },
  { title: '地域未来投資促進補助金', description: '地域の特性を活かした企業の地域経済牽引事業計画を支援。', category: '地方創生', targetType: '全事業者', level: '国', prefecture: '全国', maxAmount: 300000000n, subsidyRate: '1/2〜2/3', status: 'active', applicationUrl: 'https://www.meti.go.jp/policy/sme_chiiki/miraisouzo/' },
  { title: '食品輸出促進補助金', description: '農林水産物・食品の輸出拡大に向けた取り組みを支援。', category: '農業・林業', targetType: '農業・食品事業者', level: '国', prefecture: '全国', maxAmount: 10000000n, subsidyRate: '1/2', status: 'active', applicationUrl: 'https://www.maff.go.jp/' },
  { title: 'サイバーセキュリティ対策促進助成金', description: '中小企業のサイバーセキュリティ対策導入を支援。', category: 'IT・デジタル', targetType: '中小企業', level: '国', prefecture: '全国', maxAmount: 1500000n, subsidyRate: '1/2', status: 'active', applicationUrl: 'https://www.ipa.go.jp/' },
  { title: 'スタートアップ支援補助金（J-Startup）', description: '革新的な技術やビジネスモデルを持つスタートアップを集中支援。', category: '創業支援', targetType: 'スタートアップ', level: '国', prefecture: '全国', maxAmount: 50000000n, subsidyRate: '1/2〜2/3', status: 'active', applicationUrl: 'https://j-startup.go.jp/' },
];

const prefectureSubsidies = [
  { title: '北海道中小企業デジタル化推進補助金', description: '道内中小企業のIT活用・デジタル化を支援する補助金。', category: 'IT・デジタル', targetType: '中小企業', level: '都道府県', prefecture: '北海道', maxAmount: 2000000n, subsidyRate: '1/2', status: 'active' },
  { title: '青森県農業参入支援補助金', description: '農業への新規参入や経営拡大を目指す事業者を支援。', category: '農業・林業', targetType: '農業従事者', level: '都道府県', prefecture: '青森県', maxAmount: 5000000n, subsidyRate: '1/2', status: 'active' },
  { title: '宮城県ものづくり産業振興補助金', description: '県内製造業の技術開発・設備投資を支援。', category: '設備投資', targetType: '製造業', level: '都道府県', prefecture: '宮城県', maxAmount: 10000000n, subsidyRate: '1/2', status: 'active' },
  { title: '東京都創業助成事業', description: '都内での創業を目指す方や創業後5年未満の中小企業者を支援。', category: '創業支援', targetType: '創業者', level: '都道府県', prefecture: '東京都', maxAmount: 3000000n, subsidyRate: '2/3', status: 'active', applicationUrl: 'https://startup-station.metro.tokyo.lg.jp/' },
  { title: '東京都中小企業省エネルギー設備導入助成', description: '都内中小企業の省エネ設備導入を助成。', category: '環境・エネルギー', targetType: '中小企業', level: '都道府県', prefecture: '東京都', maxAmount: 5000000n, subsidyRate: '1/2', status: 'active' },
  { title: '大阪府中小企業融資あっせん補助金', description: '中小企業の資金調達を支援するための補助制度。', category: '経営支援', targetType: '中小企業', level: '都道府県', prefecture: '大阪府', maxAmount: 1000000n, subsidyRate: '一部補助', status: 'active' },
  { title: '愛知県ものづくり競争力強化補助金', description: '県内製造業の生産性向上・新製品開発を支援。', category: '設備投資', targetType: '製造業', level: '都道府県', prefecture: '愛知県', maxAmount: 15000000n, subsidyRate: '1/2', status: 'active' },
  { title: '福岡県スタートアップ支援補助金', description: '革新的ビジネスモデルを持つ県内スタートアップを支援。', category: '創業支援', targetType: 'スタートアップ', level: '都道府県', prefecture: '福岡県', maxAmount: 5000000n, subsidyRate: '2/3', status: 'active' },
  { title: '北海道観光産業デジタル化補助金', description: '道内観光関連事業者のデジタル化・DX推進を支援。', category: 'IT・デジタル', targetType: '観光事業者', level: '都道府県', prefecture: '北海道', maxAmount: 1500000n, subsidyRate: '2/3', status: 'active' },
  { title: '神奈川県ゼロカーボン推進補助金', description: 'CO2削減に取り組む県内事業者を対象とした補助金。', category: '環境・エネルギー', targetType: '全事業者', level: '都道府県', prefecture: '神奈川県', maxAmount: 3000000n, subsidyRate: '1/2', status: 'active' },
];

const municipalSubsidies = [
  { title: '札幌市中小企業デジタル化推進補助金', description: '市内中小企業のデジタル化・DX化を支援する補助金。', category: 'IT・デジタル', targetType: '中小企業', level: '市区町村', prefecture: '北海道', municipalityCode: '011002', municipalityName: '札幌市', maxAmount: 1000000n, subsidyRate: '1/2', status: 'active' },
  { title: '仙台市創業支援補助金', description: '市内での創業を支援するための補助制度。', category: '創業支援', targetType: '創業者', level: '市区町村', prefecture: '宮城県', municipalityCode: '041009', municipalityName: '仙台市', maxAmount: 1500000n, subsidyRate: '2/3', status: 'active' },
  { title: '名古屋市省エネ設備導入補助金', description: '市内事業者の省エネ設備・再エネ設備導入を補助。', category: '環境・エネルギー', targetType: '全事業者', level: '市区町村', prefecture: '愛知県', municipalityCode: '231003', municipalityName: '名古屋市', maxAmount: 2000000n, subsidyRate: '1/3', status: 'active' },
  { title: '大阪市女性起業家支援補助金', description: '大阪市内で起業する女性を対象とした支援補助金。', category: '創業支援', targetType: '女性起業家', level: '市区町村', prefecture: '大阪府', municipalityCode: '271004', municipalityName: '大阪市', maxAmount: 2000000n, subsidyRate: '2/3', status: 'active' },
  { title: '福岡市スタートアップ促進補助金', description: '市内スタートアップの事業化・成長を支援。', category: '創業支援', targetType: 'スタートアップ', level: '市区町村', prefecture: '福岡県', municipalityCode: '401005', municipalityName: '福岡市', maxAmount: 3000000n, subsidyRate: '2/3', status: 'active' },
  { title: '横浜市ものづくり中小企業振興補助金', description: '市内製造業の設備投資・技術開発を支援。', category: '設備投資', targetType: '製造業', level: '市区町村', prefecture: '神奈川県', municipalityCode: '141003', municipalityName: '横浜市', maxAmount: 5000000n, subsidyRate: '1/2', status: 'active' },
  { title: '京都市伝統産業振興補助金', description: '伝統工芸品の製造・販売に取り組む事業者を支援。', category: '伝統産業', targetType: '伝統産業事業者', level: '市区町村', prefecture: '京都府', municipalityCode: '261009', municipalityName: '京都市', maxAmount: 3000000n, subsidyRate: '1/2', status: 'active' },
  { title: '神戸市海洋産業振興補助金', description: '海洋関連産業の振興・新事業創出を支援。', category: '産業振興', targetType: '海洋関連事業者', level: '市区町村', prefecture: '兵庫県', municipalityCode: '281005', municipalityName: '神戸市', maxAmount: 5000000n, subsidyRate: '1/2', status: 'active' },
  { title: '広島市中小企業テレワーク導入補助金', description: 'テレワーク環境整備を行う市内中小企業を支援。', category: 'IT・デジタル', targetType: '中小企業', level: '市区町村', prefecture: '広島県', municipalityCode: '341003', municipalityName: '広島市', maxAmount: 1000000n, subsidyRate: '2/3', status: 'active' },
  { title: '熊本市農業新技術導入補助金', description: 'スマート農業等の新技術導入を支援する補助金。', category: '農業・林業', targetType: '農業従事者', level: '市区町村', prefecture: '熊本県', municipalityCode: '431009', municipalityName: '熊本市', maxAmount: 3000000n, subsidyRate: '1/2', status: 'active' },
];

const templates = [
  { title: '補助金申請書（基本テンプレート）', category: '申請書', description: '一般的な補助金申請に使用できる基本テンプレート。', fileName: 'application_basic.pdf' },
  { title: '事業計画書テンプレート', category: '事業計画書', description: 'ものづくり補助金等で必要な事業計画書の作成テンプレート。', fileName: 'business_plan.pdf' },
  { title: '収支計画書テンプレート', category: '財務書類', description: '補助事業の収支計画を作成するためのテンプレート。', fileName: 'financial_plan.pdf' },
  { title: '実績報告書テンプレート', category: '報告書', description: '補助金交付後の実績報告に使用するテンプレート。', fileName: 'result_report.pdf' },
  { title: '見積書確認チェックリスト', category: 'チェックリスト', description: '補助金申請時の見積書確認に使用するチェックリスト。', fileName: 'estimate_checklist.pdf' },
  { title: 'IT導入補助金申請書テンプレート', category: '申請書', description: 'IT導入補助金の申請に特化したテンプレート。', fileName: 'it_application.pdf' },
  { title: '雇用助成金申請書テンプレート', category: '申請書', description: '雇用関連の助成金申請に使用するテンプレート。', fileName: 'employment_application.pdf' },
];

async function main() {
  console.log('Seeding database...');

  // Admin user
  const hash = await bcrypt.hash('admin1234', 10);
  await prisma.adminUser.upsert({
    where: { email: 'admin@subsidy-navigator.jp' },
    update: {},
    create: { email: 'admin@subsidy-navigator.jp', passwordHash: hash },
  });

  // Subsidies
  const allSubsidies = [
    ...nationalSubsidies.map(s => ({ ...s, municipalityCode: undefined, municipalityName: undefined })),
    ...prefectureSubsidies.map(s => ({ ...s, municipalityCode: undefined, municipalityName: undefined })),
    ...municipalSubsidies,
  ];

  for (const sub of allSubsidies) {
    await prisma.subsidy.create({
      data: {
        title: sub.title,
        description: sub.description,
        category: sub.category,
        targetType: sub.targetType,
        level: sub.level,
        prefecture: sub.prefecture,
        municipalityCode: sub.municipalityCode ?? null,
        municipalityName: sub.municipalityName ?? null,
        maxAmount: sub.maxAmount ?? null,
        subsidyRate: sub.subsidyRate ?? null,
        status: sub.status,
        applicationUrl: (sub as any).applicationUrl ?? null,
      },
    });
  }

  // Templates
  for (const t of templates) {
    await prisma.template.upsert({
      where: { id: t.fileName },
      update: {},
      create: { id: t.fileName, ...t },
    });
  }

  console.log(`Seeded ${allSubsidies.length} subsidies and ${templates.length} templates.`);
}

main()
  .catch(console.error)
  .finally(() => prisma.$disconnect());
