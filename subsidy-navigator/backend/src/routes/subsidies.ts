import { Router, Request, Response } from 'express';
import { PrismaClient } from '@prisma/client';
import { generateSubsidyPdf } from '../services/pdf';

const router = Router();
const prisma = new PrismaClient();

router.get('/', async (req: Request, res: Response) => {
  const { prefecture, category, level, keyword, targetType, page = '1', limit = '20' } = req.query as Record<string, string>;
  const skip = (parseInt(page) - 1) * parseInt(limit);

  const where: any = { status: 'active' };
  if (prefecture) where.prefecture = prefecture;
  if (category) where.category = category;
  if (level) where.level = level;
  if (targetType) where.targetType = { contains: targetType };
  if (keyword) where.OR = [
    { title: { contains: keyword, mode: 'insensitive' } },
    { description: { contains: keyword, mode: 'insensitive' } },
  ];

  const [total, subsidies] = await Promise.all([
    prisma.subsidy.count({ where }),
    prisma.subsidy.findMany({ where, skip, take: parseInt(limit), orderBy: { createdAt: 'desc' } }),
  ]);

  res.json({ data: subsidies, meta: { total, page: parseInt(page), limit: parseInt(limit), pages: Math.ceil(total / parseInt(limit)) } });
});

router.get('/:id', async (req: Request, res: Response) => {
  const subsidy = await prisma.subsidy.findUnique({ where: { id: req.params.id } });
  if (!subsidy) return res.status(404).json({ error: 'Not found' });
  res.json({ data: subsidy });
});

router.get('/:id/pdf', async (req: Request, res: Response) => {
  const subsidy = await prisma.subsidy.findUnique({ where: { id: req.params.id } });
  if (!subsidy) return res.status(404).json({ error: 'Not found' });
  res.setHeader('Content-Type', 'application/pdf');
  res.setHeader('Content-Disposition', `attachment; filename="subsidy_${subsidy.id}.pdf"`);
  const pdfStream = generateSubsidyPdf(subsidy as any);
  pdfStream.pipe(res);
});

export default router;
