import { Card, Statistic } from 'antd';

interface KpiCardProps {
  title: string;
  value: string;
  detail: string;
  onClick?: () => void;
}

export function KpiCard({ title, value, detail, onClick }: KpiCardProps) {
  return (
    <Card hoverable={Boolean(onClick)} onClick={onClick} style={{ height: '100%' }}>
      <Statistic title={title} value={value} />
      <div style={{ marginTop: 8, color: '#8c8c8c', fontSize: 12 }}>{detail}</div>
    </Card>
  );
}
