import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

export default function Navbar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  return (
    <nav className="fixed top-0 left-0 right-0 h-14 bg-white border-b border-gray-200 z-50 flex items-center px-6">
      <div className="flex items-center justify-between w-full">
        {/* Logo */}
        <Link to="/" className="text-xl font-bold text-indigo-700 tracking-tight hover:text-indigo-800 transition">
          TM Tools
        </Link>

        {/* Right side */}
        <div className="flex items-center gap-4">
          <Link
            to="/settings"
            className="text-sm text-gray-600 hover:text-gray-900 font-medium transition"
          >
            Settings
          </Link>

          {user && (
            <span className="text-sm text-gray-500 hidden sm:block">
              {user.username}
            </span>
          )}

          <button
            onClick={handleLogout}
            className="text-sm text-gray-600 hover:text-gray-900 font-medium border border-gray-300 hover:border-gray-400 px-3 py-1.5 rounded-md transition"
          >
            Logout
          </button>
        </div>
      </div>
    </nav>
  )
}
