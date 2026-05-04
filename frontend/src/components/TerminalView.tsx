import { useEffect, useRef } from 'react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import { WebLinksAddon } from '@xterm/addon-web-links';
import '@xterm/xterm/css/xterm.css';
import { getTerminalWsUrl } from '../api';

interface Props {
  thingName: string;
}

export default function TerminalView({ thingName }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const fitRef = useRef<FitAddon | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // Create terminal
    const term = new Terminal({
      cursorBlink: true,
      fontSize: 14,
      fontFamily: 'ui-monospace, "SF Mono", Menlo, monospace',
      theme: {
        background: '#0f172a',
        foreground: '#e2e8f0',
        cursor: '#e2e8f0',
        selectionBackground: '#334155',
        black: '#0f172a',
        red: '#f87171',
        green: '#4ade80',
        yellow: '#facc15',
        blue: '#60a5fa',
        magenta: '#c084fc',
        cyan: '#22d3ee',
        white: '#e2e8f0',
        brightBlack: '#64748b',
        brightRed: '#fca5a5',
        brightGreen: '#86efac',
        brightYellow: '#fde047',
        brightBlue: '#93c5fd',
        brightMagenta: '#d8b4fe',
        brightCyan: '#67e8f9',
        brightWhite: '#f8fafc',
      },
    });

    const fitAddon = new FitAddon();
    const webLinksAddon = new WebLinksAddon();
    term.loadAddon(fitAddon);
    term.loadAddon(webLinksAddon);

    term.open(container);
    fitAddon.fit();

    termRef.current = term;
    fitRef.current = fitAddon;

    term.writeln('\x1b[90mConnecting...\x1b[0m');

    // Connect WebSocket
    const url = getTerminalWsUrl(thingName);
    const ws = new WebSocket(url);
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;

    ws.onopen = () => {
      // Connection established, waiting for device ACK
    };

    ws.onmessage = (event) => {
      if (typeof event.data === 'string') {
        // Control message
        const msg = JSON.parse(event.data);
        if (msg.type === 'connected') {
          term.clear();
        } else if (msg.type === 'error') {
          term.writeln(`\r\n\x1b[31m${msg.message}\x1b[0m`);
        } else if (msg.type === 'closed') {
          term.writeln(`\r\n\x1b[90m[Session ended (exit code: ${msg.exit_code})]\x1b[0m`);
        }
      } else {
        // Binary: PTY output
        const data = new Uint8Array(event.data);
        term.write(data);
      }
    };

    ws.onclose = () => {
      term.writeln('\r\n\x1b[90m[Disconnected]\x1b[0m');
    };

    ws.onerror = () => {
      term.writeln('\r\n\x1b[31m[Connection error]\x1b[0m');
    };

    // Send keystrokes as binary
    term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        const encoder = new TextEncoder();
        ws.send(encoder.encode(data));
      }
    });

    // Send binary data (paste, etc.)
    term.onBinary((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        const bytes = new Uint8Array(data.length);
        for (let i = 0; i < data.length; i++) {
          bytes[i] = data.charCodeAt(i);
        }
        ws.send(bytes);
      }
    });

    // Send resize events
    term.onResize(({ cols, rows }) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'resize', cols, rows }));
      }
    });

    // ResizeObserver to refit terminal
    const resizeObserver = new ResizeObserver(() => {
      fitAddon.fit();
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      ws.close();
      term.dispose();
      termRef.current = null;
      wsRef.current = null;
      fitRef.current = null;
    };
  }, [thingName]);

  return <div ref={containerRef} className="terminal-container" />;
}
