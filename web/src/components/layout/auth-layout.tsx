import { Outlet } from 'react-router-dom'
import { Logo } from './brand'
export function AuthLayout() { return <div className="auth-page"><header className="site-header"><Logo to="/login" /></header><Outlet /><footer><span>© 2025 PromptVault, Inc. All rights reserved.</span><span>Privacy　 Terms　 Status　 Contact</span></footer></div> }
