import type { ImgHTMLAttributes } from 'react';
export default function Image({unoptimized:_unoptimized,priority:_priority,...props}:ImgHTMLAttributes<HTMLImageElement>&{unoptimized?:boolean;priority?:boolean}){return <img {...props}/>;}
