import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { Toaster } from 'sonner';
import { useAuthStore } from '@/stores/authStore';
import { MainLayout } from '@/components/layout/MainLayout';
import LoginPage from '@/pages/LoginPage';
import RegisterPage from '@/pages/RegisterPage';
import DashboardPage from '@/pages/DashboardPage';
import KtDiagnosisPage from '@/pages/KtDiagnosisPage';

/* ── Auth guard ─────────────────────────────────────────────── */
function ProtectedRoute() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <Outlet />;
}

function GuestRoute() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  if (isAuthenticated) return <Navigate to="/dashboard/chat" replace />;
  return <Outlet />;
}

/* KT standalone 模式才挂载 iframe 入口;integrated 模式下 KT 直接走主对话流,
   不需要独立路由 */
const KT_STANDALONE = import.meta.env.VITE_KT_STANDALONE === 'true';

/* ── App ────────────────────────────────────────────────────── */
export default function App() {
  return (
    <BrowserRouter>
      <Toaster
        position="top-right"
        richColors
        closeButton
        toastOptions={{ duration: 4000 }}
      />
      <Routes>
        {/* Guest */}
        <Route element={<GuestRoute />}>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
        </Route>

        {/* Protected */}
        <Route element={<ProtectedRoute />}>
          <Route path="/dashboard" element={<MainLayout />}>
            <Route index element={<Navigate to="chat" replace />} />
            <Route path="chat" element={<DashboardPage />} />
            <Route path="chat/:conversationId" element={<DashboardPage />} />
            {KT_STANDALONE && (
              <Route path="kt-diagnosis" element={<KtDiagnosisPage />} />
            )}
          </Route>
        </Route>

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/dashboard/chat" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
