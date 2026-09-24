import { redirect } from 'next/navigation';
import { ApiError } from '@/lib/api/server';
import { listConversations } from '@/lib/db/conversations';
import type { Conversation } from '@/lib/api/types';
import FloatingSidebar from '@/components/chat/FloatingSidebar';

/**
 * Chat layout — full-viewport height, no body overflow.
 *
 * The chat view fills exactly 100dvh minus the 64px app header, with zero
 * page-level scrollbars. All scrolling happens inside the messages area inside
 * ChatInterface. The floating sidebar is absolutely positioned over the canvas.
 *
 * Structure:
 *   <div relative h-full>          ← positioning context for the floating sidebar
 *     <FloatingSidebar />           ← absolutely positioned, overlays the canvas
 *     {children}                    ← ChatInterface fills the full area
 *   </div>
 */
export default async function ChatLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // A backend 401 (expired/absent API session) is a signed-out visitor too —
  // same login redirect as every other screen behind auth. The middleware gates
  // on cookie presence; the backend validates the session here.
  let conversations: Conversation[];
  try {
    conversations = await listConversations();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      redirect('/login');
    }
    throw err;
  }

  // FloatingSidebar still speaks the old ConversationRow shape (components are a
  // later slice). The backend Conversation carries no user_id — ownership is
  // server-side now — and the list UI never reads it, so the adapter fills it
  // with an empty string. Delete this adapter when the sidebar migrates.
  const sidebarConversations = conversations.map((c) => ({ ...c, user_id: '' }));

  return (
    <div
      className="relative overflow-hidden chat-no-hscroll"
      style={{ height: 'calc(100dvh - 64px)' }}
    >
      {/* Floating sidebar — absolutely positioned over the chat canvas */}
      <FloatingSidebar conversations={sidebarConversations} />

      {/* Chat content — fills full area; ChatInterface manages internal scroll */}
      <div className="h-full overflow-hidden" id="chat-main">
        {children}
      </div>
    </div>
  );
}
