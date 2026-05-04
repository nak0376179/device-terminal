import { useState } from 'react';
import { login } from '../api';

interface Props {
  onLogin: (token: string) => void;
}

export default function LoginForm({ onLogin }: Props) {
  const [groupId, setGroupId] = useState('');
  const [groupPw, setGroupPw] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const token = await login(groupId, groupPw);
      onLogin(token);
    } catch {
      setError('グループIDまたはパスワードが正しくありません');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-wrap">
      <form className="login-form" onSubmit={handleSubmit}>
        <h2>Device Terminal</h2>
        {error && <div className="error">{error}</div>}
        <label>
          グループ ID
          <input
            value={groupId}
            onChange={(e) => setGroupId(e.target.value)}
            autoFocus
            required
          />
        </label>
        <label>
          パスワード
          <input
            type="password"
            value={groupPw}
            onChange={(e) => setGroupPw(e.target.value)}
            required
          />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? 'ログイン中…' : 'ログイン'}
        </button>
      </form>
    </div>
  );
}
