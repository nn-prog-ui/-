import { Router, Request, Response } from 'express';
import { PrismaClient } from '@prisma/client';
import { sendAlertVerificationEmail } from '../services/email';

const router = Router();
const prisma = new PrismaClient();

router.post('/', async (req: Request, res: Response) => {
  const { email, prefectures, categories, keywords, municipalityCodes } = req.body;
  if (!email) return res.status(400).json({ error: 'Email is required' });
  const alert = await prisma.alert.create({
    data: { email, prefectures: prefectures || [], categories: categories || [], keywords: keywords || [], municipalityCodes: municipalityCodes || [] },
  });
  await sendAlertVerificationEmail(email, alert.token);
  res.json({ data: alert, message: '確認メールを送信しました' });
});

router.get('/verify/:token', async (req: Request, res: Response) => {
  const alert = await prisma.alert.findUnique({ where: { token: req.params.token } });
  if (!alert) return res.status(404).json({ error: 'Invalid token' });
  await prisma.alert.update({ where: { id: alert.id }, data: { verified: true } });
  res.json({ message: 'アラートが有効化されました' });
});

router.delete('/:id', async (req: Request, res: Response) => {
  await prisma.alert.update({ where: { id: req.params.id }, data: { active: false } });
  res.json({ message: '解除しました' });
});

export default router;
