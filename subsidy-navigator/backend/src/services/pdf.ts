import PDFDocument from 'pdfkit';
import { Subsidy, Municipality } from '@prisma/client';

type SubsidyWithMunicipality = Subsidy & { municipality: Municipality };

function formatAmount(amount: number | null): string {
  if (!amount) return '要問合せ';
  if (amount >= 100000000) return `${amount / 100000000}億円`;
  if (amount >= 10000) return `${Math.floor(amount / 10000)}万円`;
  return `${amount.toLocaleString()}円`;
}

function formatDate(date: Date | null): string {
  if (!date) return '未定';
  return new Date(date).toLocaleDateString('ja-JP', { year: 'numeric', month: 'long', day: 'numeric' });
}

function drawHeader(doc: InstanceType<typeof PDFDocument>, title: string) {
  // Header background
  doc.rect(0, 0, doc.page.width, 80).fill('#1e3a5f');

  // Title
  doc.fillColor('white')
    .fontSize(20)
    .text('補助金ナビ', 50, 20);

  doc.fontSize(13)
    .fillColor('#93c5fd')
    .text(title, 50, 48);

  // Reset position
  doc.fillColor('#1e1e1e').moveDown(3);
}

function drawFooter(doc: InstanceType<typeof PDFDocument>) {
  const bottom = doc.page.height - 50;
  doc.moveTo(50, bottom - 10).lineTo(doc.page.width - 50, bottom - 10).strokeColor('#e5e7eb').stroke();
  doc.fillColor('#9ca3af')
    .fontSize(10)
    .text(`補助金ナビ | 生成日: ${new Date().toLocaleDateString('ja-JP')}`, 50, bottom, {
      align: 'center',
      width: doc.page.width - 100,
    });
}

function drawSectionTitle(doc: InstanceType<typeof PDFDocument>, title: string) {
  doc.rect(50, doc.y, doc.page.width - 100, 28).fill('#f3f4f6');
  doc.fillColor('#1e3a5f')
    .fontSize(13)
    .font('Helvetica-Bold')
    .text(title, 60, doc.y - 22);
  doc.font('Helvetica').moveDown(0.5);
}

export async function generateSubsidyReport(
  subsidies: SubsidyWithMunicipality[]
): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    const doc = new PDFDocument({ margin: 50, size: 'A4' });
    const buffers: Buffer[] = [];

    doc.on('data', (chunk: Buffer) => buffers.push(chunk));
    doc.on('end', () => resolve(Buffer.concat(buffers)));
    doc.on('error', reject);

    drawHeader(doc, '補助金一覧レポート');

    // Summary info
    doc.fillColor('#374151')
      .fontSize(11)
      .text(`総件数: ${subsidies.length}件`, { continued: true })
      .text(`  |  生成日: ${new Date().toLocaleDateString('ja-JP')}`, { align: 'right' });

    doc.moveDown(1);

    // Table header
    const colX = { num: 50, title: 75, municipality: 300, amount: 420, deadline: 500 };
    const headerY = doc.y;

    doc.rect(50, headerY, doc.page.width - 100, 24).fill('#1e3a5f');
    doc.fillColor('white').fontSize(10);
    doc.text('No.', colX.num, headerY + 7);
    doc.text('補助金名', colX.title, headerY + 7);
    doc.text('自治体', colX.municipality, headerY + 7);
    doc.text('上限額', colX.amount, headerY + 7);
    doc.text('締切', colX.deadline, headerY + 7);

    doc.moveDown(0.5);

    subsidies.forEach((subsidy, index) => {
      if (doc.y > doc.page.height - 100) {
        doc.addPage();
        drawHeader(doc, '補助金一覧レポート（続き）');
      }

      const rowY = doc.y;
      const rowBg = index % 2 === 0 ? '#ffffff' : '#f9fafb';

      doc.rect(50, rowY, doc.page.width - 100, 24).fill(rowBg);
      doc.fillColor('#374151').fontSize(9);
      doc.text(`${index + 1}`, colX.num, rowY + 7);
      doc.text(subsidy.title.substring(0, 28), colX.title, rowY + 7);
      doc.text(subsidy.municipality.name, colX.municipality, rowY + 7);
      doc.text(formatAmount(subsidy.maxAmount), colX.amount, rowY + 7);
      doc.text(formatDate(subsidy.applicationPeriodEnd), colX.deadline, rowY + 7);

      // Light border
      doc.moveTo(50, rowY + 24).lineTo(doc.page.width - 50, rowY + 24).strokeColor('#e5e7eb').stroke();

      doc.moveDown(0.5);
    });

    doc.moveDown(2);

    // Category summary
    drawSectionTitle(doc, 'カテゴリ別集計');

    const categories = subsidies.reduce((acc, s) => {
      acc[s.category] = (acc[s.category] || 0) + 1;
      return acc;
    }, {} as Record<string, number>);

    Object.entries(categories).sort((a, b) => b[1] - a[1]).forEach(([category, count]) => {
      const barWidth = Math.min((count / subsidies.length) * 300, 300);
      const barY = doc.y;

      doc.fillColor('#6b7280').fontSize(10).text(category, 60, barY, { width: 150 });
      doc.rect(220, barY + 2, barWidth, 12).fill('#3b82f6');
      doc.fillColor('#374151').text(`${count}件`, 530, barY);

      doc.moveDown(0.8);
    });

    drawFooter(doc);
    doc.end();
  });
}

export async function generateApplicationTemplate(
  subsidy: SubsidyWithMunicipality
): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    const doc = new PDFDocument({ margin: 50, size: 'A4' });
    const buffers: Buffer[] = [];

    doc.on('data', (chunk: Buffer) => buffers.push(chunk));
    doc.on('end', () => resolve(Buffer.concat(buffers)));
    doc.on('error', reject);

    drawHeader(doc, '補助金申請書テンプレート');

    // Subsidy title
    doc.fillColor('#1e3a5f')
      .fontSize(18)
      .font('Helvetica-Bold')
      .text(subsidy.title, { align: 'center' });

    doc.moveDown(0.5);

    doc.fillColor('#6b7280')
      .fontSize(12)
      .font('Helvetica')
      .text(`${subsidy.municipality.name} (${subsidy.municipality.prefecture})`, { align: 'center' });

    doc.moveDown(1.5);

    // Info table
    const infoItems = [
      ['カテゴリ', subsidy.category],
      ['対象事業者', subsidy.targetBusiness || '詳細要確認'],
      ['補助上限額', formatAmount(subsidy.maxAmount)],
      ['申請期間', `${formatDate(subsidy.applicationPeriodStart)} 〜 ${formatDate(subsidy.applicationPeriodEnd)}`],
      ['ステータス', subsidy.status === 'OPEN' ? '募集中' : subsidy.status === 'CLOSED' ? '受付終了' : '予定'],
    ];

    infoItems.forEach(([label, value]) => {
      const itemY = doc.y;
      doc.rect(50, itemY, 150, 26).fill('#f3f4f6');
      doc.rect(200, itemY, doc.page.width - 250, 26).fill('#ffffff').stroke('#e5e7eb');

      doc.fillColor('#1e3a5f').fontSize(11).font('Helvetica-Bold')
        .text(label, 60, itemY + 8);
      doc.fillColor('#374151').fontSize(11).font('Helvetica')
        .text(value, 210, itemY + 8);

      doc.moveDown(1);
    });

    doc.moveDown(1);

    // Description
    drawSectionTitle(doc, '補助金概要');
    doc.fillColor('#374151').fontSize(11).font('Helvetica')
      .text(subsidy.description, 60, doc.y + 5, {
        width: doc.page.width - 120,
        lineGap: 4,
      });

    doc.moveDown(2);

    // Application fields
    drawSectionTitle(doc, '申請者情報（記入例）');

    const fields = [
      '申請者氏名・代表者氏名',
      '法人名・屋号',
      '法人番号（法人の場合）',
      '所在地（郵便番号・住所）',
      '電話番号',
      'メールアドレス',
      '業種・事業内容',
      '従業員数',
      '資本金（法人の場合）',
    ];

    fields.forEach(field => {
      if (doc.y > doc.page.height - 120) {
        doc.addPage();
      }
      const fieldY = doc.y;
      doc.fillColor('#6b7280').fontSize(10)
        .text(field, 60, fieldY);
      doc.moveTo(60, fieldY + 16).lineTo(doc.page.width - 60, fieldY + 16)
        .strokeColor('#d1d5db').stroke();
      doc.moveDown(1.5);
    });

    doc.moveDown(1);

    // Application content section
    if (doc.y > doc.page.height - 200) {
      doc.addPage();
    }

    drawSectionTitle(doc, '申請内容');

    const contentFields = [
      { label: '補助事業のタイトル', lines: 1 },
      { label: '事業の目的・概要', lines: 3 },
      { label: '補助対象経費の内訳', lines: 4 },
      { label: '期待される効果', lines: 2 },
      { label: '実施スケジュール', lines: 2 },
    ];

    contentFields.forEach(({ label, lines }) => {
      if (doc.y > doc.page.height - (lines * 20 + 60)) {
        doc.addPage();
      }
      const fieldY = doc.y + 5;
      doc.fillColor('#6b7280').fontSize(10).text(label, 60, fieldY);
      doc.moveDown(0.5);

      for (let i = 0; i < lines; i++) {
        const lineY = doc.y;
        doc.moveTo(60, lineY).lineTo(doc.page.width - 60, lineY)
          .strokeColor('#d1d5db').stroke();
        doc.moveDown(1.2);
      }
      doc.moveDown(0.5);
    });

    // Note box
    doc.moveDown(1);
    const noteY = doc.y;
    doc.rect(50, noteY, doc.page.width - 100, 60).fill('#fef3c7').stroke('#f59e0b');
    doc.fillColor('#92400e').fontSize(11).font('Helvetica-Bold')
      .text('注意事項', 60, noteY + 8);
    doc.font('Helvetica').fontSize(10)
      .text('本テンプレートは参考用です。実際の申請書式は各自治体のウェブサイトでご確認ください。', 60, noteY + 26, {
        width: doc.page.width - 120,
      });

    drawFooter(doc);
    doc.end();
  });
}
