import { Router, Request, Response } from 'express';
import { PrismaClient } from '@prisma/client';
import { sendConsultingConfirmation } from '../services/email';

const router = Router();
const prisma = new PrismaClient();

router.post('/', async (req: Request, res: Response) => {
  const { name, email, company, phone, prefecture, industry, employees, budget, message } = req.body;
  if (!name || !email || !message) return res.status(400).json({ error: 'name, email, message are required' });
  const request = await prisma.consultingRequest.create({ data: { name, email, company, phone, prefecture, industry, employees, budget, message } });
  await sendConsultingConfirmation(name, email);
  res.json({ data: request, message: 'ご相談を受け付けました' });
});

export default router;
