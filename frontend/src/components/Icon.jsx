const paths = {
 map: 'M3 5l6-2 6 2 6-2v16l-6 2-6-2-6 2V5zm6-2v16m6-14v16', activity: 'M3 12h4l3-8 4 16 3-8h4',
 compass: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zm4 5-3 5-5 3 3-5 5-3z', layers: 'm3 8 9-5 9 5-9 5-9-5zm0 5 9 5 9-5m-18 5 9 5 9-5',
 plus: 'M12 5v14M5 12h14', minus: 'M5 12h14', close: 'm6 6 12 12M6 18 18 6', target: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zm0-5v3m0 12v3M3 12h3m12 0h3',
 arrow: 'M12 20V4m-7 7 7-7 7 7', play: 'm8 5 11 7-11 7V5z', pause: 'M8 5v14M16 5v14', reset: 'M4 10a8 8 0 1 1 1 8M4 4v6h6', chevron: 'm9 5 7 7-7 7',
 shield: 'm12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3zm-4 9 3 3 5-6', book: 'M12 5C8 2 3 4 3 4v15s5-2 9 1c4-3 9-1 9-1V4s-5-2-9 1v15',
 expand: 'M3 9V3h6m6 0h6v6M3 15v6h6m6 0h6v-6', chat: 'M4 4h16v12H9l-5 4V4z', watch: 'M8 3V1h8v2m-8 18v2h8v-2M7 5h10v14H7V5z', wind: 'M3 8h12a3 3 0 1 0-3-3M3 12h16a3 3 0 1 1-3 3M3 16h5', check: 'm5 12 4 4L19 6',
 cloud: 'M7 18a4 4 0 0 1-.5-8A6 6 0 0 1 18 9.5a4.3 4.3 0 0 1-.5 8.5H7z', tornado: 'M4 5h16M6 9h12M9 13h8M11 17h4M12 21h1', sun: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zm0-6v3m0 14v3M2 12h3m14 0h3M5 5l2 2m10 10 2 2m0-14-2 2M7 17l-2 2', droplet: 'M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z', battery: 'M3 8h15v8H3V8zm18 3v2M6 11v2', alert: 'm12 3 10 18H2L12 3zm0 6v5m0 3v1',
};
export default function Icon({ name, size = 20, ...props }) { return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}><path d={paths[name] ?? paths.compass}/></svg>; }
