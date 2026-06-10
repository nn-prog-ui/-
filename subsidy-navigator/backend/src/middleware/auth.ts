import { Request, Response, NextFunction } from 'express';
import jwt from 'jsonwebtoken';

export function requireAdmin(req: Request, res: Response, next: NextFunction) {
  const auth = req.headers.authorization;
  if (!auth?.startsWith('Bearer ')) return res.status(401).json({ error: 'Unauthorized' });
  try {
    const payload = jwt.verify(auth.slice(7), process.env.JWT_SECRET || 'secret');
    (req as any).admin = payload;
    next();
  } catch {
    res.status(401).json({ error: 'Invalid token' });
  }
}
