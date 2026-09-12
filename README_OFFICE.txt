========================================================================
 KEA LINK WATCH -- OFFICE COMPUTER GUIDE
 (no coding knowledge needed -- just follow the numbered steps)
========================================================================

WHAT THIS IS
------------
A program that watches the KEA counselling pages listed in
config\link_watch_pages.txt and posts a message to our Telegram
group whenever a NEW link appears on one of them. It runs on THIS
computer, which is why it must stay switched on.

To watch a different or additional page, open
config\link_watch_pages.txt in Notepad and add its web address on
its own line (or remove a line to stop watching a page). No coding
needed -- just save the file.


ONE-TIME SETUP (do this once, the first time)
------------------------------------------------------------------------

STEP 1 -- Install Python (skip if already installed)

   Go to:  https://www.python.org/downloads/
   Click the big yellow "Download Python" button and run the
   installer.

   IMPORTANT: on the very first screen of the installer, there is a
   checkbox near the bottom that says:

        [ ] Add python.exe to PATH

   TICK THAT BOX before clicking Install. If you miss this, the
   next steps won't work and you'll need to reinstall.


STEP 2 -- Double-click SETUP.bat

   Find the folder this file is in, and double-click SETUP.bat.
   A black window will open and print what it's doing. This
   downloads and installs everything the program needs -- it can
   take a few minutes, especially the first time (it downloads a
   small web browser component too). Just wait for it to finish.

   If it prints a red [PROBLEM] message, read it -- it explains
   what to do in plain English. Otherwise, when you see:

        Setup complete!

   you're done with this step. Press any key to close the window.


STEP 3 -- Put your tokens in config\.env

   Inside the folder, open the "config" folder, then open the file
   named ".env" using Notepad (right-click it -> Open with -> Notepad).

   Fill in the four lines so they look like this (with YOUR real
   values, not these examples):

        TELEGRAM_BOT_TOKEN=123456789:AAbc-realtoken-goes-here
        TELEGRAM_CHAT_ID=-1001234567890
        HEALTH_BOT_TOKEN=987654321:AAxyz-realtoken-goes-here
        HEALTH_CHAT_ID=-1009876543210

   (Whoever set up the Telegram groups/bots has these values.)
   Save the file (Ctrl+S) and close Notepad.


THAT'S IT -- SETUP IS DONE. Now choose how you want to run it:


ABOUT THE VERY FIRST RUN
------------------------------------------------------------------------
Whichever option you pick below, the FIRST time it ever runs on this
computer it will pause and print:

   First run on this computer -- setting the starting point.

This checks the watched pages once and remembers every link already
on them, WITHOUT sending anything to Telegram. It only happens this
one time. This matters because without it, the very first real check
would think EVERY existing link is brand new and try to alert on all
of them at once -- this step prevents that. After it finishes
("Starting point set."), normal checking begins and only genuinely
NEW links from that point on get sent to Telegram.


DAY-TO-DAY: HOW TO RUN IT
------------------------------------------------------------------------

OPTION A -- Run it now, watch it work (a window stays open)

   Double-click START_MONITOR.bat

   A window opens and stays open, checking every 1 minute. You
   can leave this window open in the background as long as you like.
   CLOSING THE WINDOW STOPS THE MONITOR. Use this option if you want
   to watch it, or for a quick one-off run.


OPTION B -- Set it and forget it (no window, always running)

   Double-click INSTALL_AUTOSTART.bat  (do this ONCE)

   This registers the monitor to run automatically in the background,
   every 1 minute, with NO window to keep open -- even after this
   computer restarts (as long as someone is logged in, which on a
   24/7 office PC is basically always). This is the recommended way
   to run it long-term.

   To STOP the background mode later: double-click
   UNINSTALL_AUTOSTART.bat

You do not need to run BOTH options -- pick one. Most offices should
use Option B (INSTALL_AUTOSTART.bat) and forget about it.


WHAT "THE GREEN CHECK IN TELEGRAM" MEANS
------------------------------------------------------------------------
Every 1 minute, the monitor posts a short status line to the
HEALTH Telegram group:

   [Green check] Run #12 OK -- everything checked fine this time.
   [Red cross]   Run #12 FAILED -- something went wrong this time.

This HEALTH group is just a heartbeat -- it does not mean anything
new was found. The MAIN Telegram group is where real alerts appear
(a newly-added link on one of the watched pages).

If you stop seeing the green check messages for more than about
5 minutes, something has stopped -- see below.


IF SOMETHING GOES WRONG
------------------------------------------------------------------------
- No green checks for 5+ minutes:
    The computer may have gone to sleep, lost internet, or the
    window (if using Option A) got closed. Check the computer is
    on, connected to the internet, and re-run START_MONITOR.bat
    or reboot (Option B resumes automatically on login).

- A window shows a [PROBLEM] message:
    Read it -- it's written in plain English and tells you the fix
    (usually: re-check config\.env, or check the internet
    connection).

- Nothing above helps, or you're not sure:
    Call/message: ______________________  (fill in who to contact)

- It seems to be sending old / already-known links, or way too many
  messages at once:
    This should only ever happen on a genuinely first run (see "ABOUT
    THE VERY FIRST RUN" above) -- if it happens again later, something
    is wrong. To reset: close any open monitor window (Option A) or
    run UNINSTALL_AUTOSTART.bat (Option B), then delete the folder
    named "data" inside this program's folder, then start it again
    (START_MONITOR.bat or INSTALL_AUTOSTART.bat). It will re-run the
    "setting the starting point" step and settle down. Ask for help
    if it keeps happening.


A FEW THINGS TO KNOW
------------------------------------------------------------------------
- This computer must stay switched ON and connected to the internet
  for the monitor to work -- that's the whole point of running it
  here rather than "in the cloud" (the counselling website only
  allows connections from inside India, and this office is inside
  India).
- Nobody needs to touch this computer day-to-day once Option B is
  set up -- just don't turn it off.
- Your Telegram tokens live only in config\.env on this computer.
  Never share that file or paste its contents anywhere online.
========================================================================
