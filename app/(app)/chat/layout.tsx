import { redirect } from 'next/navigation';
import { createClient } from '@/lib/supabase/server';
import { listConversations } from '@/lib/db/conversations';
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
  // Auth guard — redirect unauthenticated users to login
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect('/login');
  }

  const conversations = await listConversations(supabase, user.id);

  return (
    <div
      className="relative overflow-hidden chat-no-hscroll"
      style={{ height: 'calc(100dvh - 64px)' }}
    >
      {/* Floating sidebar — absolutely positioned over the chat canvas */}
      <FloatingSidebar conversations={conversations} />

      {/* Chat content — fills full area; ChatInterface manages internal scroll */}
      <div className="h-full overflow-hidden" id="chat-main">
        {children}
      </div>
    </div>
  );
}
