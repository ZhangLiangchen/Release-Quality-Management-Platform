import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { Spin } from 'antd';
import { useSession } from '../app/SessionContext';

export function RequireAuth() {
  const { isAuthenticated, loading } = useSession();
  const location = useLocation();

  if (loading) {
    return <Spin fullscreen />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <Outlet />;
}
