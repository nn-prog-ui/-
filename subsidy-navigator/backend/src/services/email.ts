import nodemailer from 'nodemailer';
import { Alert, ConsultingRequest, Subsidy, Municipality } from '@prisma/client';
import { logger } from '../index';

type SubsidyWithMunicipality = Subsidy & { municipality: Municipality };

function createTransporter() {
  return nodemailer.createTransport({
    host: process.env.SMTP_HOST || 'smtp.gmail.com',
    port: parseInt(process.env.SMTP_PORT || '587', 10),
    secure: false,
    auth: {
      user: process.env.SMTP_USER || '',
      pass: process.env.SMTP_PASS || '',
    },
  });
}

const FROM_ADDRESS = `補助金ナビ <${process.env.SMTP_USER || 'noreply@subsidy-navigator.jp'}>`;

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

export async function sendAlertEmail(
  alert: Alert,
  newSubsidies: SubsidyWithMunicipality[]
): Promise<void> {
  if (newSubsidies.length === 0) return;

  const subsidyRows = newSubsidies.map(s => `
    <tr>
      <td style="padding: 12px; border-bottom: 1px solid #e5e7eb;">
        <strong style="color: #1e3a5f;">${s.title}</strong><br>
        <span style="color: #6b7280; font-size: 13px;">${s.municipality.name} (${s.municipality.prefecture})</span>
      </td>
      <td style="padding: 12px; border-bottom: 1px solid #e5e7eb; text-align: center;">
        <span style="background: #dbeafe; color: #1d4ed8; padding: 2px 8px; border-radius: 9999px; font-size: 12px;">${s.category}</span>
      </td>
      <td style="padding: 12px; border-bottom: 1px solid #e5e7eb; text-align: right; color: #059669; font-weight: bold;">
        最大 ${formatAmount(s.maxAmount)}
      </td>
      <td style="padding: 12px; border-bottom: 1px solid #e5e7eb; text-align: center; font-size: 13px;">
        ${formatDate(s.applicationPeriodEnd)}まで
      </td>
    </tr>
  `).join('');

  const html = `
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>補助金アラート</title>
</head>
<body style="font-family: 'Hiragino Sans', 'Yu Gothic', sans-serif; background: #f9fafb; margin: 0; padding: 20px;">
  <div style="max-width: 700px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
    <div style="background: #1e3a5f; padding: 24px 32px;">
      <h1 style="color: white; margin: 0; font-size: 22px;">補助金ナビ アラート通知</h1>
      <p style="color: #93c5fd; margin: 8px 0 0; font-size: 14px;">新しい補助金情報が${newSubsidies.length}件見つかりました</p>
    </div>
    <div style="padding: 24px 32px;">
      <p style="color: #374151;">ご登録いただいたアラート条件に合致する補助金情報をお届けします。</p>
      <table style="width: 100%; border-collapse: collapse; margin-top: 16px;">
        <thead>
          <tr style="background: #f3f4f6;">
            <th style="padding: 10px 12px; text-align: left; font-size: 13px; color: #6b7280;">補助金名 / 自治体</th>
            <th style="padding: 10px 12px; text-align: center; font-size: 13px; color: #6b7280;">カテゴリ</th>
            <th style="padding: 10px 12px; text-align: right; font-size: 13px; color: #6b7280;">補助上限額</th>
            <th style="padding: 10px 12px; text-align: center; font-size: 13px; color: #6b7280;">締切</th>
          </tr>
        </thead>
        <tbody>
          ${subsidyRows}
        </tbody>
      </table>
      <div style="margin-top: 24px; text-align: center;">
        <a href="${process.env.FRONTEND_URL || 'http://localhost:3000'}/subsidies"
           style="background: #f97316; color: white; padding: 12px 32px; border-radius: 6px; text-decoration: none; font-weight: bold; display: inline-block;">
          詳細を確認する
        </a>
      </div>
    </div>
    <div style="background: #f9fafb; padding: 16px 32px; border-top: 1px solid #e5e7eb;">
      <p style="color: #9ca3af; font-size: 12px; margin: 0;">
        アラートの解除・変更は
        <a href="${process.env.FRONTEND_URL || 'http://localhost:3000'}/alerts" style="color: #6b7280;">こちら</a>
        から行えます。
      </p>
    </div>
  </div>
</body>
</html>
  `;

  try {
    const transporter = createTransporter();
    await transporter.sendMail({
      from: FROM_ADDRESS,
      to: alert.email,
      subject: `【補助金ナビ】新着補助金情報 ${newSubsidies.length}件`,
      html,
    });
    logger.info(`Alert email sent to ${alert.email}`);
  } catch (error) {
    logger.error(`Failed to send alert email to ${alert.email}:`, error);
    throw error;
  }
}

export async function sendWeeklyDigest(
  email: string,
  subsidies: SubsidyWithMunicipality[]
): Promise<void> {
  const topSubsidies = subsidies.slice(0, 10);

  const cards = topSubsidies.map(s => `
    <div style="border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; margin-bottom: 16px;">
      <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
        <h3 style="color: #1e3a5f; margin: 0; font-size: 16px;">${s.title}</h3>
        <span style="background: #dbeafe; color: #1d4ed8; padding: 2px 8px; border-radius: 9999px; font-size: 12px; white-space: nowrap; margin-left: 8px;">${s.category}</span>
      </div>
      <p style="color: #6b7280; font-size: 13px; margin: 0 0 8px;">${s.municipality.name} (${s.municipality.prefecture})</p>
      <p style="color: #374151; font-size: 14px; margin: 0 0 8px;">${s.description.substring(0, 100)}...</p>
      <div style="display: flex; justify-content: space-between; font-size: 13px;">
        <span style="color: #059669; font-weight: bold;">最大 ${formatAmount(s.maxAmount)}</span>
        <span style="color: #6b7280;">締切: ${formatDate(s.applicationPeriodEnd)}</span>
      </div>
    </div>
  `).join('');

  const html = `
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <title>週間補助金ダイジェスト</title>
</head>
<body style="font-family: 'Hiragino Sans', 'Yu Gothic', sans-serif; background: #f9fafb; margin: 0; padding: 20px;">
  <div style="max-width: 700px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
    <div style="background: #1e3a5f; padding: 24px 32px;">
      <h1 style="color: white; margin: 0; font-size: 22px;">週間補助金ダイジェスト</h1>
      <p style="color: #93c5fd; margin: 8px 0 0; font-size: 14px;">今週の注目補助金情報 ${topSubsidies.length}件</p>
    </div>
    <div style="padding: 24px 32px;">
      <p style="color: #374151; margin-bottom: 24px;">今週の注目補助金情報をお届けします。申請期限をご確認の上、ぜひご活用ください。</p>
      ${cards}
      <div style="margin-top: 24px; text-align: center;">
        <a href="${process.env.FRONTEND_URL || 'http://localhost:3000'}/subsidies"
           style="background: #1e3a5f; color: white; padding: 12px 32px; border-radius: 6px; text-decoration: none; font-weight: bold; display: inline-block;">
          すべての補助金を見る
        </a>
      </div>
    </div>
    <div style="background: #f9fafb; padding: 16px 32px; border-top: 1px solid #e5e7eb;">
      <p style="color: #9ca3af; font-size: 12px; margin: 0;">
        配信停止は
        <a href="${process.env.FRONTEND_URL || 'http://localhost:3000'}/alerts" style="color: #6b7280;">こちら</a>
      </p>
    </div>
  </div>
</body>
</html>
  `;

  try {
    const transporter = createTransporter();
    await transporter.sendMail({
      from: FROM_ADDRESS,
      to: email,
      subject: '【補助金ナビ】週間補助金ダイジェスト',
      html,
    });
    logger.info(`Weekly digest sent to ${email}`);
  } catch (error) {
    logger.error(`Failed to send weekly digest to ${email}:`, error);
    throw error;
  }
}

export async function sendConsultingConfirmation(request: ConsultingRequest): Promise<void> {
  const html = `
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <title>相談申込確認</title>
</head>
<body style="font-family: 'Hiragino Sans', 'Yu Gothic', sans-serif; background: #f9fafb; margin: 0; padding: 20px;">
  <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
    <div style="background: #1e3a5f; padding: 24px 32px;">
      <h1 style="color: white; margin: 0; font-size: 22px;">補助金ナビ</h1>
      <p style="color: #93c5fd; margin: 8px 0 0; font-size: 14px;">専門家相談 申込確認</p>
    </div>
    <div style="padding: 24px 32px;">
      <p style="color: #374151;">${request.name} 様</p>
      <p style="color: #374151;">このたびは補助金ナビへ専門家相談をお申し込みいただき、誠にありがとうございます。</p>
      <p style="color: #374151;">以下の内容でお申し込みを受け付けました。担当者より2営業日以内にご連絡いたします。</p>

      <div style="background: #f9fafb; border-radius: 8px; padding: 16px; margin: 24px 0;">
        <h3 style="color: #1e3a5f; margin: 0 0 16px; font-size: 15px;">お申し込み内容</h3>
        <table style="width: 100%; border-collapse: collapse;">
          <tr>
            <td style="padding: 8px 0; color: #6b7280; font-size: 14px; width: 120px;">お名前</td>
            <td style="padding: 8px 0; color: #374151; font-size: 14px;">${request.name}</td>
          </tr>
          ${request.company ? `
          <tr>
            <td style="padding: 8px 0; color: #6b7280; font-size: 14px;">会社名</td>
            <td style="padding: 8px 0; color: #374151; font-size: 14px;">${request.company}</td>
          </tr>` : ''}
          <tr>
            <td style="padding: 8px 0; color: #6b7280; font-size: 14px;">メール</td>
            <td style="padding: 8px 0; color: #374151; font-size: 14px;">${request.email}</td>
          </tr>
          ${request.prefecture ? `
          <tr>
            <td style="padding: 8px 0; color: #6b7280; font-size: 14px;">都道府県</td>
            <td style="padding: 8px 0; color: #374151; font-size: 14px;">${request.prefecture}</td>
          </tr>` : ''}
          <tr>
            <td style="padding: 8px 0; color: #6b7280; font-size: 14px; vertical-align: top;">ご相談内容</td>
            <td style="padding: 8px 0; color: #374151; font-size: 14px;">${request.message}</td>
          </tr>
          <tr>
            <td style="padding: 8px 0; color: #6b7280; font-size: 14px;">申込日時</td>
            <td style="padding: 8px 0; color: #374151; font-size: 14px;">${formatDate(request.createdAt)}</td>
          </tr>
        </table>
      </div>

      <p style="color: #374151; font-size: 14px;">ご不明な点がございましたら、お気軽にお問い合わせください。</p>
    </div>
    <div style="background: #f9fafb; padding: 16px 32px; border-top: 1px solid #e5e7eb;">
      <p style="color: #9ca3af; font-size: 12px; margin: 0;">補助金ナビ | subsidy-navigator.jp</p>
    </div>
  </div>
</body>
</html>
  `;

  try {
    const transporter = createTransporter();
    await transporter.sendMail({
      from: FROM_ADDRESS,
      to: request.email,
      subject: '【補助金ナビ】専門家相談のお申し込みを受け付けました',
      html,
    });
    logger.info(`Consulting confirmation sent to ${request.email}`);
  } catch (error) {
    logger.error(`Failed to send consulting confirmation to ${request.email}:`, error);
    throw error;
  }
}
