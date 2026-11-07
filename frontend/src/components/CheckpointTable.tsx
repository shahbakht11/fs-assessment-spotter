import { memo } from 'react'
import { fmtTime } from '../lib/format'
import { levelColor, levelLabel } from '../lib/risk'
import type { Checkpoint } from '../lib/types'

interface Props {
  checkpoints: Checkpoint[]
  onFocus: (cp: Checkpoint) => void
}

const fmt = (v: number | null, digits: number) => (v == null ? '—' : v.toFixed(digits))

/** Every checkpoint for the selected route; click a row to fly the map there. */
export const CheckpointTable = memo(function CheckpointTable({ checkpoints, onFocus }: Props) {
  return (
    <div className="cp-table-wrap">
      <table className="cp-table">
        <thead>
          <tr>
            <th>Mile</th>
            <th>ETA</th>
            <th>Risk</th>
            <th title="Sustained wind, mph">Wind</th>
            <th title="Rain, in/hr">Rain</th>
            <th title="Snow, in/hr">Snow</th>
          </tr>
        </thead>
        <tbody>
          {checkpoints.map((cp) => (
            <tr key={cp.mi} onClick={() => onFocus(cp)} tabIndex={0} onKeyDown={(e) => e.key === 'Enter' && onFocus(cp)}>
              <td>{Math.round(cp.mi)}</td>
              <td className="nowrap">{fmtTime(cp.eta)}</td>
              <td>
                <span className="dot" style={{ background: levelColor(cp.level) }} />
                {levelLabel(cp.level)}
              </td>
              <td className={cp.factor === 'wind' ? 'driver' : ''}>{fmt(cp.wind, 0)}</td>
              <td className={cp.factor === 'rain' ? 'driver' : ''}>{fmt(cp.rain, 2)}</td>
              <td className={cp.factor === 'snow' ? 'driver' : ''}>{fmt(cp.snow, 1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
})
