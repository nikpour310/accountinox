export function requireRole(user: any, role: string) {
  if (!user) throw new Error('unauthorized');
  if (user.role !== role) throw new Error('forbidden');
}

export function hasAnyRole(user: any, roles: string[]) {
  if (!user) return false;
  return roles.includes(user.role);
}
