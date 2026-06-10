import { Router, Request, Response, NextFunction } from 'express';
import { PrismaClient } from '@prisma/client';
import { generateApplicationTemplate } from '../services/pdf';
import { createError } from '../middleware/errorHandler';

const router = Router();
const prisma = new PrismaClient();

// GET /api/templates
router.get('/', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { category } = req.query;

    const where: Record<string, unknown> = {};
    if (category) where.category = category as string;

    const templates = await prisma.template.findMany({
      where,
      orderBy: [{ downloadCount: 'desc' }, { createdAt: 'desc' }],
    });

    res.json({
      data: templates,
      error: null,
      meta: { total: templates.length },
    });
  } catch (err) {
    next(err);
  }
});

// GET /api/templates/:id
router.get('/:id', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const template = await prisma.template.findUnique({
      where: { id: req.params.id },
    });

    if (!template) {
      return next(createError('テンプレートが見つかりません', 404));
    }

    res.json({ data: template, error: null, meta: {} });
  } catch (err) {
    next(err);
  }
});

// GET /api/templates/:id/download
router.get('/:id/download', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const template = await prisma.template.findUnique({
      where: { id: req.params.id },
    });

    if (!template) {
      return next(createError('テンプレートが見つかりません', 404));
    }

    // Increment download count
    await prisma.template.update({
      where: { id: template.id },
      data: { downloadCount: { increment: 1 } },
    });

    // Generate PDF for the template
    const templateSubsidy = {
      id: template.id,
      title: template.title,
      description: template.content,
      category: template.category,
      targetBusiness: '中小企業・小規模事業者',
      maxAmount: null,
      applicationPeriodStart: null,
      applicationPeriodEnd: null,
      status: 'OPEN' as const,
      municipalityId: '',
      scrapeUrl: null,
      scrapedAt: null,
      createdAt: template.createdAt,
      updatedAt: template.updatedAt,
      municipality: {
        id: '',
        code: '',
        name: '各自治体',
        prefecture: '',
        population: null,
        website: null,
        createdAt: new Date(),
        updatedAt: new Date(),
      },
    };

    const pdfBuffer = await generateApplicationTemplate(templateSubsidy);

    res.setHeader('Content-Type', 'application/pdf');
    res.setHeader('Content-Disposition', `attachment; filename="template-${template.id}.pdf"`);
    res.send(pdfBuffer);
  } catch (err) {
    next(err);
  }
});

export default router;
