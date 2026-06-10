import { Router, Request, Response, NextFunction } from 'express';
import { PrismaClient } from '@prisma/client';

const router = Router();
const prisma = new PrismaClient();

// GET /api/municipalities
router.get('/', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { prefecture } = req.query;

    const where: Record<string, unknown> = {};
    if (prefecture) {
      where.prefecture = prefecture as string;
    }

    const municipalities = await prisma.municipality.findMany({
      where,
      orderBy: [{ prefecture: 'asc' }, { name: 'asc' }],
    });

    // Get subsidy counts
    const counts = await prisma.subsidy.groupBy({
      by: ['municipalityId'],
      _count: true,
      where: { status: 'OPEN' },
    });

    const countMap = new Map(counts.map(c => [c.municipalityId, c._count]));

    const enriched = municipalities.map(m => ({
      ...m,
      openSubsidyCount: countMap.get(m.id) || 0,
    }));

    res.json({
      data: enriched,
      error: null,
      meta: { total: municipalities.length },
    });
  } catch (err) {
    next(err);
  }
});

// GET /api/municipalities/prefectures
router.get('/prefectures', async (_req: Request, res: Response, next: NextFunction) => {
  try {
    const prefectures = await prisma.municipality.findMany({
      select: { prefecture: true },
      distinct: ['prefecture'],
      orderBy: { prefecture: 'asc' },
    });

    res.json({
      data: prefectures.map(p => p.prefecture),
      error: null,
      meta: { total: prefectures.length },
    });
  } catch (err) {
    next(err);
  }
});

// GET /api/municipalities/:code
router.get('/:code', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const municipality = await prisma.municipality.findUnique({
      where: { code: req.params.code },
      include: {
        subsidies: {
          where: { status: 'OPEN' },
          orderBy: { createdAt: 'desc' },
          take: 10,
        },
      },
    });

    if (!municipality) {
      res.status(404).json({ error: '自治体が見つかりません', data: null, meta: {} });
      return;
    }

    res.json({ data: municipality, error: null, meta: {} });
  } catch (err) {
    next(err);
  }
});

export default router;
