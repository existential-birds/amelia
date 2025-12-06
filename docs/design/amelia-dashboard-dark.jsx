import React, { useState, useEffect, useRef } from 'react';
import { MapPin, GitBranch, Users, Package, History, Target, Cloud, Radio, Send } from 'lucide-react';

const AmeliaDashboardDark = () => {
  const [nodesVisible, setNodesVisible] = useState(false);
  const [edgesDrawn, setEdgesDrawn] = useState(false);
  const [activeNode, setActiveNode] = useState('developer');
  const [selectedFlight, setSelectedFlight] = useState('#8');

  useEffect(() => {
    // Instrument panel startup sequence
    const timer1 = setTimeout(() => setNodesVisible(true), 200);
    const timer2 = setTimeout(() => setEdgesDrawn(true), 800);
    return () => {
      clearTimeout(timer1);
      clearTimeout(timer2);
    };
  }, []);

  const workflows = [
    { id: '#8', name: 'Create reviewer agent benchmark framework', status: 'in-progress', eta: '02:45' },
    { id: '#7', name: 'Add meaningful CLI integration tests', status: 'completed', eta: '00:00' },
    { id: '#9', name: 'Handle clarification requests from Claude', status: 'queued', eta: '04:30' },
    { id: '#5', name: 'Multi-agent workflow system', status: 'blocked', eta: '--:--' },
  ];

  const logEntries = [
    { time: '14:32:07Z', agent: 'ARCHITECT', msg: 'Issue #8 parsed. Creating task DAG for benchmark framework.' },
    { time: '14:32:45Z', agent: 'ARCHITECT', msg: 'Plan approved. Routing to DEVELOPER.' },
    { time: '14:33:12Z', agent: 'DEVELOPER', msg: 'Task received. Scaffolding tests/benchmark/ structure.' },
    { time: '14:34:02Z', agent: 'DEVELOPER', msg: 'Created benchmark_runner.py with pytest-benchmark.' },
    { time: '14:35:18Z', agent: 'DEVELOPER', msg: 'Added reviewer accuracy metrics. 186 lines.' },
    { time: '14:36:22Z', agent: 'REVIEWER', msg: 'Code review commenced. Checking test coverage.' },
    { time: '14:37:01Z', agent: 'REVIEWER', msg: 'Missing edge case: empty diff handling. Requesting revision.' },
  ];

  const nodes = [
    { id: 'issue', label: 'Issue', subtitle: 'Origin', x: 100, y: 160, status: 'completed' },
    { id: 'architect', label: 'Architect', subtitle: 'Planning', x: 250, y: 160, status: 'completed' },
    { id: 'developer', label: 'Developer', subtitle: 'Implementation', x: 400, y: 160, status: 'active' },
    { id: 'reviewer', label: 'Reviewer', subtitle: 'Code Review', x: 550, y: 160, status: 'pending' },
    { id: 'done', label: 'Done', subtitle: 'Complete', x: 700, y: 160, status: 'pending' },
  ];

  const edges = [
    { from: 'issue', to: 'architect', label: '0:12', status: 'completed' },
    { from: 'architect', to: 'developer', label: '0:33', status: 'completed' },
    { from: 'developer', to: 'reviewer', label: '1:42', bidirectional: true, status: 'active' },
    { from: 'reviewer', to: 'done', label: '0:08', status: 'pending' },
  ];

  return (
    <div style={styles.container}>
      {/* Starfield background */}
      <div style={styles.starfield} />
      
      {/* Subtle scan lines for cockpit glass effect */}
      <div style={styles.cockpitGlass} />
      
      {/* Vignette - deeper for night flight */}
      <div style={styles.vignette} />

      {/* Sidebar - instrument panel left */}
      <aside style={styles.sidebar}>
        <div style={styles.logoContainer}>
          <h1 style={styles.logo}>AMELIA</h1>
          <p style={styles.logoSubtitle}>AGENTIC ORCHESTRATOR</p>
        </div>

        <nav style={styles.nav}>
          <div style={styles.navSection}>
            <span style={styles.navSectionLabel}>WORKFLOWS</span>
            <NavItem icon={<GitBranch size={14} />} label="Active Jobs" active />
            <NavItem icon={<Users size={14} />} label="Agents" />
            <NavItem icon={<Package size={14} />} label="Outputs" />
          </div>
          <div style={styles.navSection}>
            <span style={styles.navSectionLabel}>HISTORY</span>
            <NavItem icon={<History size={14} />} label="Past Runs" />
            <NavItem icon={<Target size={14} />} label="Milestones" />
            <NavItem icon={<Cloud size={14} />} label="Deployments" />
          </div>
          <div style={styles.navSection}>
            <span style={styles.navSectionLabel}>MONITORING</span>
            <NavItem icon={<Radio size={14} />} label="Logs" />
            <NavItem icon={<Send size={14} />} label="Notifications" />
          </div>
        </nav>

        <div style={styles.sidebarFooter}>
          <div style={styles.compassRose}>
            <svg width="48" height="48" viewBox="0 0 48 48">
              <circle cx="24" cy="24" r="20" fill="none" stroke="#EFF8E2" strokeWidth="1" opacity="0.2"/>
              <path d="M24 4 L26 24 L24 44 L22 24 Z" fill="#EFF8E2" opacity="0.15"/>
              <path d="M4 24 L24 22 L44 24 L24 26 Z" fill="#EFF8E2" opacity="0.15"/>
              <path d="M24 8 L26 24 L24 20 L22 24 Z" fill="#FFC857"/>
              <circle cx="24" cy="24" r="3" fill="#0D1A12"/>
            </svg>
          </div>
          <span style={styles.footerText}>v2.4.1</span>
        </div>
      </aside>

      {/* Main Content */}
      <main style={styles.main}>
        {/* Header */}
        <header style={styles.header}>
          <div style={styles.headerLeft}>
            <span style={styles.headerLabel}>WORKFLOW</span>
            <h2 style={styles.headerTitle}>{selectedFlight}</h2>
          </div>
          <div style={styles.headerCenter}>
            <div style={styles.etaDisplay}>
              <span style={styles.etaLabel}>EST. COMPLETION</span>
              <span style={styles.etaValue}>02:45</span>
            </div>
          </div>
          <div style={styles.headerRight}>
            <div style={styles.statusIndicator}>
              <div style={styles.statusDot} />
              <span style={styles.statusText}>RUNNING</span>
            </div>
          </div>
        </header>

        {/* Grid background for graph area */}
        <div style={styles.graphSection}>
          <div style={styles.gridBackground} />
          
          {/* Workflow Graph - Flight Tracking Map */}
          <svg style={styles.graphSvg} viewBox="0 0 800 320">
            <defs>
              {/* Bearing lines pattern - 45° angles */}
              <pattern id="bearingGrid" width="40" height="40" patternUnits="userSpaceOnUse">
                <path d="M 0 40 L 40 0" fill="none" stroke="#EFF8E2" strokeWidth="0.5" opacity="0.04"/>
                <path d="M 0 0 L 40 40" fill="none" stroke="#EFF8E2" strokeWidth="0.5" opacity="0.04"/>
              </pattern>
              {/* Latitude/longitude grid */}
              <pattern id="navGrid" width="80" height="80" patternUnits="userSpaceOnUse">
                <rect width="80" height="80" fill="url(#bearingGrid)"/>
                <path d="M 80 0 L 0 0 0 80" fill="none" stroke="#EFF8E2" strokeWidth="0.8" opacity="0.08"/>
              </pattern>
              {/* Glow filter for active elements */}
              <filter id="instrumentGlow" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur stdDeviation="3" result="blur"/>
                <feComposite in="SourceGraphic" in2="blur" operator="over"/>
              </filter>
            </defs>
            
            {/* Background grid */}
            <rect width="800" height="320" fill="url(#navGrid)"/>
            
            {/* Compass rose watermark */}
            <g opacity="0.06" transform="translate(400, 160)">
              <circle r="100" fill="none" stroke="#EFF8E2" strokeWidth="1"/>
              <circle r="70" fill="none" stroke="#EFF8E2" strokeWidth="0.5"/>
              <path d="M 0 -110 L 0 110" stroke="#EFF8E2" strokeWidth="1"/>
              <path d="M -110 0 L 110 0" stroke="#EFF8E2" strokeWidth="1"/>
              <path d="M -78 -78 L 78 78" stroke="#EFF8E2" strokeWidth="0.5"/>
              <path d="M -78 78 L 78 -78" stroke="#EFF8E2" strokeWidth="0.5"/>
              <text x="0" y="-85" textAnchor="middle" fontSize="12" fill="#EFF8E2" fontFamily="'Barlow Condensed', sans-serif">N</text>
            </g>

            {/* String connections - rendered first so pins appear on top */}
            {edges.map((edge, i) => {
              const fromNode = nodes.find(n => n.id === edge.from);
              const toNode = nodes.find(n => n.id === edge.to);
              const isCompleted = edge.status === 'completed';
              const isPending = edge.status === 'pending';
              const isActive = edge.status === 'active';
              const pathLength = Math.abs(toNode.x - fromNode.x);
              const midX = (fromNode.x + toNode.x) / 2;
              
              return (
                <g key={`edge-${i}`}>
                  {/* String/route line */}
                  <line
                    x1={fromNode.x}
                    y1={fromNode.y}
                    x2={toNode.x}
                    y2={toNode.y}
                    stroke={isActive ? '#FFC857' : '#EFF8E2'}
                    strokeWidth={isCompleted || isActive ? '2' : '1.5'}
                    strokeDasharray={isCompleted ? 'none' : '8 4'}
                    opacity={isPending ? 0.2 : (isCompleted ? 0.5 : 0.8)}
                    strokeDashoffset={edgesDrawn ? 0 : pathLength}
                    filter={isActive ? 'url(#instrumentGlow)' : 'none'}
                    style={{
                      transition: 'stroke-dashoffset 0.8s ease-out',
                      transitionDelay: `${i * 0.15}s`
                    }}
                  />
                  
                  {/* Traveled route overlay for completed */}
                  {isCompleted && (
                    <line
                      x1={fromNode.x}
                      y1={fromNode.y}
                      x2={toNode.x}
                      y2={toNode.y}
                      stroke="#5B8A72"
                      strokeWidth="2"
                      opacity="0.6"
                    />
                  )}
                  
                  {/* Duration label - positioned above the line */}
                  <g
                    opacity={edgesDrawn ? 1 : 0}
                    style={{ transition: 'opacity 0.3s ease-out', transitionDelay: `${0.8 + i * 0.1}s` }}
                  >
                    <rect
                      x={midX - 18}
                      y={fromNode.y - 32}
                      width="36"
                      height="16"
                      fill="#0D1A12"
                      stroke="rgba(239, 248, 226, 0.2)"
                      strokeWidth="0.5"
                    />
                    <text
                      x={midX}
                      y={fromNode.y - 21}
                      fill="#88A896"
                      fontSize="10"
                      fontFamily="'IBM Plex Mono', monospace"
                      textAnchor="middle"
                    >
                      {edge.label}
                    </text>
                  </g>
                  
                  {/* Direction indicator - small arrow */}
                  <polygon
                    points={`${midX + 20},${fromNode.y} ${midX + 12},${fromNode.y - 4} ${midX + 12},${fromNode.y + 4}`}
                    fill="#EFF8E2"
                    opacity={edgesDrawn ? (isPending ? 0.15 : 0.4) : 0}
                    style={{ transition: 'opacity 0.3s ease-out', transitionDelay: `${0.6 + i * 0.1}s` }}
                  />
                </g>
              );
            })}

            {/* Location Pin Nodes */}
            {nodes.map((node, i) => {
              const isActive = node.status === 'active';
              const isCompleted = node.status === 'completed';
              const isPending = node.status === 'pending';
              const isBlocked = node.status === 'blocked';
              
              return (
                <g
                  key={node.id}
                  style={{
                    opacity: nodesVisible ? 1 : 0,
                    transform: nodesVisible ? 'translateY(0)' : 'translateY(8px)',
                    transition: 'all 0.4s ease-out',
                    transitionDelay: `${i * 0.08}s`,
                  }}
                  className="workflow-node"
                >
                  {/* MapPin icon using foreignObject */}
                  <foreignObject
                    x={node.x - 16}
                    y={node.y - 40}
                    width="32"
                    height="40"
                  >
                    <div style={{
                      width: '100%',
                      height: '100%',
                      display: 'flex',
                      alignItems: 'flex-start',
                      justifyContent: 'center',
                    }}>
                      <MapPin
                        size={32}
                        fill={isCompleted ? '#5B8A72' : isActive ? '#FFC857' : isBlocked ? '#C94A3A' : '#4A5C54'}
                        color={isCompleted ? '#3D5E4B' : isActive ? '#D4A53D' : isBlocked ? '#922A1E' : '#2D3B35'}
                        strokeWidth={1.5}
                        className={isActive ? 'beacon-pulse' : ''}
                        style={isActive ? { filter: 'drop-shadow(0 0 8px rgba(255, 200, 87, 0.6))' } : {}}
                      />
                    </div>
                  </foreignObject>
                  
                  {/* Location label below */}
                  <text
                    x={node.x}
                    y={node.y + 16}
                    fill="#EFF8E2"
                    fontSize="11"
                    fontFamily="'Barlow Condensed', sans-serif"
                    fontWeight="600"
                    textAnchor="middle"
                    letterSpacing="0.05em"
                  >
                    {node.label}
                  </text>
                  <text
                    x={node.x}
                    y={node.y + 28}
                    fill="#88A896"
                    fontSize="9"
                    fontFamily="'Source Sans 3', sans-serif"
                    textAnchor="middle"
                  >
                    {node.subtitle}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>

        {/* Bottom Section */}
        <div style={styles.bottomSection}>
          {/* Workflow Queue */}
          <div style={styles.queuePanel}>
            <h3 style={styles.panelTitle}>JOB QUEUE</h3>
            <div style={styles.queueList}>
              {workflows.map((wf, i) => (
                <div
                  key={wf.id}
                  style={{
                    ...styles.queueItem,
                    ...(wf.id === selectedFlight ? styles.queueItemActive : {}),
                    animationDelay: `${i * 0.1}s`
                  }}
                  onClick={() => setSelectedFlight(wf.id)}
                >
                  <div style={styles.queueItemHeader}>
                    <span style={styles.queueItemId}>{wf.id}</span>
                    <StatusBadge status={wf.status} />
                  </div>
                  <p style={styles.queueItemName}>{wf.name}</p>
                  <span style={styles.queueItemEta}>Est: {wf.eta}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Activity Log */}
          <div style={styles.logPanel}>
            <h3 style={styles.panelTitle}>ACTIVITY LOG</h3>
            <div style={styles.logContainer}>
              <div style={styles.scanLines} />
              {logEntries.map((entry, i) => (
                <div key={i} style={styles.logEntry}>
                  <span style={styles.logTime}>{entry.time}</span>
                  <span style={styles.logAgent}>[{entry.agent}]</span>
                  <span style={styles.logMsg}>{entry.msg}</span>
                </div>
              ))}
              <div style={styles.logCursor}>▋</div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};

const NavItem = ({ icon, label, active }) => (
  <div style={{ ...styles.navItem, ...(active ? styles.navItemActive : {}) }}>
    <span style={styles.navIcon}>{icon}</span>
    <span style={styles.navLabel}>{label}</span>
  </div>
);

const StatusBadge = ({ status }) => {
  const colors = {
    'in-progress': { bg: '#FFC857', text: '#1F332E' },
    'completed': { bg: '#5B8A72', text: '#EFF8E2' },
    'queued': { bg: '#4A5C54', text: '#EFF8E2' },
    'blocked': { bg: '#C94A3A', text: '#EFF8E2' },
  };
  const labels = {
    'in-progress': 'RUNNING',
    'completed': 'DONE',
    'queued': 'QUEUED',
    'blocked': 'BLOCKED',
  };
  return (
    <span style={{ 
      ...styles.badge, 
      backgroundColor: colors[status].bg,
      color: colors[status].text,
    }}>
      {labels[status]}
    </span>
  );
};

// Dark mode color palette
// Background: #1F332E (cockpit at night)
// Primary text: #EFF8E2 (instrument backlighting)
// Active elements: #FFC857 (luminous instrument needles)
// Accent: #5B9BD5 (brightened #0A2463 for visibility)
// Secondary: #88A896 (muted instrument readings)
// Deep background: #0D1A12 (instrument panel depth)

const styles = {
  container: {
    display: 'flex',
    minHeight: '100vh',
    backgroundColor: '#1F332E',
    fontFamily: "'Source Sans 3', sans-serif",
    position: 'relative',
    overflow: 'hidden',
  },
  starfield: {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    background: `
      radial-gradient(1px 1px at 20px 30px, #EFF8E2, transparent),
      radial-gradient(1px 1px at 40px 70px, rgba(239, 248, 226, 0.8), transparent),
      radial-gradient(1px 1px at 50px 160px, rgba(239, 248, 226, 0.6), transparent),
      radial-gradient(1px 1px at 90px 40px, #EFF8E2, transparent),
      radial-gradient(1px 1px at 130px 80px, rgba(239, 248, 226, 0.7), transparent),
      radial-gradient(1.5px 1.5px at 160px 120px, #FFC857, transparent),
      radial-gradient(1px 1px at 200px 50px, rgba(239, 248, 226, 0.5), transparent),
      radial-gradient(1px 1px at 220px 150px, rgba(239, 248, 226, 0.9), transparent),
      radial-gradient(1px 1px at 280px 20px, rgba(239, 248, 226, 0.6), transparent),
      radial-gradient(1.5px 1.5px at 320px 100px, rgba(91, 155, 213, 0.8), transparent),
      radial-gradient(1px 1px at 350px 180px, rgba(239, 248, 226, 0.7), transparent),
      radial-gradient(1px 1px at 400px 60px, #EFF8E2, transparent),
      radial-gradient(1px 1px at 450px 130px, rgba(239, 248, 226, 0.5), transparent),
      radial-gradient(1px 1px at 500px 30px, rgba(239, 248, 226, 0.8), transparent),
      radial-gradient(1.5px 1.5px at 550px 90px, #FFC857, transparent),
      radial-gradient(1px 1px at 600px 170px, rgba(239, 248, 226, 0.6), transparent),
      radial-gradient(1px 1px at 650px 50px, rgba(239, 248, 226, 0.9), transparent),
      radial-gradient(1px 1px at 700px 120px, rgba(239, 248, 226, 0.4), transparent),
      radial-gradient(1px 1px at 750px 80px, #EFF8E2, transparent),
      radial-gradient(1px 1px at 800px 160px, rgba(239, 248, 226, 0.7), transparent)
    `,
    backgroundRepeat: 'repeat',
    backgroundSize: '800px 200px',
    opacity: 0.4,
    pointerEvents: 'none',
    zIndex: 0,
  },
  cockpitGlass: {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    background: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(239, 248, 226, 0.01) 2px, rgba(239, 248, 226, 0.01) 4px)',
    pointerEvents: 'none',
    zIndex: 1000,
  },
  vignette: {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    background: 'radial-gradient(ellipse at center, transparent 30%, rgba(13, 26, 18, 0.6) 100%)',
    pointerEvents: 'none',
    zIndex: 999,
  },
  sidebar: {
    width: '240px',
    backgroundColor: '#0D1A12',
    color: '#EFF8E2',
    display: 'flex',
    flexDirection: 'column',
    position: 'relative',
    zIndex: 10,
    borderRight: '1px solid rgba(239, 248, 226, 0.08)',
  },
  logoContainer: {
    padding: '28px 20px',
    borderBottom: '1px solid rgba(239, 248, 226, 0.08)',
    textAlign: 'center',
  },
  logo: {
    fontFamily: "'Bebas Neue', 'Josefin Sans', sans-serif",
    fontSize: '32px',
    fontWeight: 700,
    letterSpacing: '0.12em',
    margin: 0,
    color: '#FFC857',
    textShadow: '0 0 20px rgba(255, 200, 87, 0.3)',
  },
  logoSubtitle: {
    fontFamily: "'Barlow Condensed', sans-serif",
    fontSize: '10px',
    letterSpacing: '0.15em',
    color: '#88A896',
    margin: '4px 0 0 0',
  },
  nav: {
    flex: 1,
    padding: '20px 0',
  },
  navSection: {
    marginBottom: '24px',
  },
  navSectionLabel: {
    display: 'block',
    fontFamily: "'Barlow Condensed', sans-serif",
    fontSize: '10px',
    fontWeight: 600,
    letterSpacing: '0.15em',
    color: '#5B8A72',
    padding: '0 20px 8px',
  },
  navItem: {
    display: 'flex',
    alignItems: 'center',
    padding: '10px 20px',
    cursor: 'pointer',
    borderLeft: '3px solid transparent',
    transition: 'all 0.2s ease',
    color: '#88A896',
  },
  navItemActive: {
    borderLeftColor: '#FFC857',
    backgroundColor: 'rgba(255, 200, 87, 0.1)',
    color: '#EFF8E2',
  },
  navIcon: {
    marginRight: '12px',
    opacity: 0.8,
    display: 'flex',
    alignItems: 'center',
  },
  navLabel: {
    fontFamily: "'Barlow Condensed', sans-serif",
    fontSize: '13px',
    fontWeight: 600,
    letterSpacing: '0.05em',
    textTransform: 'uppercase',
  },
  sidebarFooter: {
    padding: '20px',
    borderTop: '1px solid rgba(239, 248, 226, 0.08)',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '12px',
  },
  compassRose: {
    opacity: 0.8,
  },
  footerText: {
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: '9px',
    color: '#5B8A72',
    letterSpacing: '0.05em',
  },
  main: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    position: 'relative',
    zIndex: 5,
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '20px 32px',
    borderBottom: '1px solid rgba(239, 248, 226, 0.1)',
    backgroundColor: 'rgba(13, 26, 18, 0.5)',
  },
  headerLeft: {},
  headerLabel: {
    fontFamily: "'Barlow Condensed', sans-serif",
    fontSize: '10px',
    fontWeight: 600,
    letterSpacing: '0.15em',
    color: '#88A896',
    display: 'block',
    marginBottom: '4px',
  },
  headerTitle: {
    fontFamily: "'Bebas Neue', 'Josefin Sans', sans-serif",
    fontSize: '28px',
    fontWeight: 700,
    letterSpacing: '0.08em',
    color: '#EFF8E2',
    margin: 0,
  },
  headerCenter: {},
  etaDisplay: {
    textAlign: 'center',
  },
  etaLabel: {
    fontFamily: "'Barlow Condensed', sans-serif",
    fontSize: '10px',
    fontWeight: 600,
    letterSpacing: '0.15em',
    color: '#88A896',
    display: 'block',
    marginBottom: '4px',
  },
  etaValue: {
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: '24px',
    fontWeight: 600,
    color: '#FFC857',
    textShadow: '0 0 10px rgba(255, 200, 87, 0.4)',
  },
  headerRight: {},
  statusIndicator: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '8px 16px',
    backgroundColor: 'rgba(255, 200, 87, 0.1)',
    border: '1px solid rgba(255, 200, 87, 0.3)',
  },
  statusDot: {
    width: '8px',
    height: '8px',
    borderRadius: '50%',
    backgroundColor: '#FFC857',
    boxShadow: '0 0 8px rgba(255, 200, 87, 0.6)',
    animation: 'pulse 2s ease-in-out infinite',
  },
  statusText: {
    fontFamily: "'Barlow Condensed', sans-serif",
    fontSize: '12px',
    fontWeight: 600,
    letterSpacing: '0.1em',
    color: '#FFC857',
  },
  graphSection: {
    position: 'relative',
    padding: '20px 32px',
    flex: 1,
    minHeight: '300px',
  },
  gridBackground: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    opacity: 0.5,
  },
  graphSvg: {
    width: '100%',
    height: '100%',
    minHeight: '300px',
  },
  bottomSection: {
    display: 'grid',
    gridTemplateColumns: '320px 1fr',
    gap: '24px',
    padding: '0 32px 32px',
  },
  queuePanel: {
    backgroundColor: 'rgba(13, 26, 18, 0.6)',
    border: '1px solid rgba(239, 248, 226, 0.1)',
    padding: '20px',
  },
  panelTitle: {
    fontFamily: "'Barlow Condensed', sans-serif",
    fontSize: '12px',
    fontWeight: 600,
    letterSpacing: '0.12em',
    color: '#88A896',
    margin: '0 0 16px 0',
    paddingBottom: '12px',
    borderBottom: '1px solid rgba(239, 248, 226, 0.1)',
  },
  queueList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
  },
  queueItem: {
    padding: '12px',
    backgroundColor: 'rgba(31, 51, 46, 0.6)',
    border: '1px solid rgba(239, 248, 226, 0.08)',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  queueItemActive: {
    borderColor: '#FFC857',
    borderWidth: '2px',
    backgroundColor: 'rgba(255, 200, 87, 0.08)',
    boxShadow: '0 0 15px rgba(255, 200, 87, 0.1)',
  },
  queueItemHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '6px',
  },
  queueItemId: {
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: '12px',
    fontWeight: 600,
    color: '#5B9BD5',
  },
  badge: {
    fontFamily: "'Barlow Condensed', sans-serif",
    fontSize: '9px',
    fontWeight: 600,
    letterSpacing: '0.08em',
    padding: '3px 8px',
  },
  queueItemName: {
    fontFamily: "'Source Sans 3', sans-serif",
    fontSize: '14px',
    color: '#EFF8E2',
    margin: '0 0 4px 0',
  },
  queueItemEta: {
    fontFamily: "'Barlow Condensed', sans-serif",
    fontSize: '11px',
    color: '#88A896',
    letterSpacing: '0.05em',
  },
  logPanel: {
    backgroundColor: 'rgba(13, 26, 18, 0.6)',
    border: '1px solid rgba(239, 248, 226, 0.1)',
    padding: '20px',
    position: 'relative',
    overflow: 'hidden',
  },
  logContainer: {
    position: 'relative',
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: '11px',
    lineHeight: '1.8',
  },
  scanLines: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    background: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(239, 248, 226, 0.015) 2px, rgba(239, 248, 226, 0.015) 4px)',
    pointerEvents: 'none',
  },
  logEntry: {
    display: 'grid',
    gridTemplateColumns: '90px 90px 1fr',
    gap: '12px',
    padding: '4px 0',
    borderBottom: '1px solid rgba(239, 248, 226, 0.04)',
  },
  logTime: {
    color: '#5B8A72',
  },
  logAgent: {
    color: '#5B9BD5',
    fontWeight: 600,
  },
  logMsg: {
    color: '#C8D9CE',
  },
  logCursor: {
    color: '#FFC857',
    textShadow: '0 0 8px rgba(255, 200, 87, 0.6)',
    animation: 'blink 1s step-end infinite',
    marginTop: '8px',
  },
};

// Add keyframes via style tag
const styleSheet = document.createElement('style');
styleSheet.textContent = `
  @import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Barlow+Condensed:wght@400;600&family=Source+Sans+3:wght@400;600&family=IBM+Plex+Mono:wght@400;600&display=swap');
  
  @keyframes pulse {
    0%, 100% { opacity: 1; box-shadow: 0 0 8px rgba(255, 200, 87, 0.6); }
    50% { opacity: 0.6; box-shadow: 0 0 12px rgba(255, 200, 87, 0.8); }
  }
  
  @keyframes blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0; }
  }
  
  @keyframes beaconPulse {
    0%, 100% { 
      transform: scale(1);
      filter: drop-shadow(0 0 6px rgba(255, 200, 87, 0.7));
    }
    50% { 
      transform: scale(1.08);
      filter: drop-shadow(0 0 12px rgba(255, 200, 87, 1));
    }
  }
  
  .beacon-pulse {
    animation: beaconPulse 1.5s ease-in-out infinite;
    transform-origin: center;
  }
  
  .workflow-node:hover {
    transform: translateY(-2px);
    filter: drop-shadow(0 4px 12px rgba(255, 200, 87, 0.15));
  }
`;
document.head.appendChild(styleSheet);

export default AmeliaDashboardDark;
