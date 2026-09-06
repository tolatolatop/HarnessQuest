import { ConfigProvider, DatePicker } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import dayjs, { type Dayjs } from 'dayjs';
import 'dayjs/locale/zh-cn';
import { t } from '../../../config/i18n';

dayjs.locale('zh-cn');

export type DateTimeRange = { from: string; to: string };

type DateTimeRangePickerProps = {
  value: DateTimeRange;
  onChange: (value: DateTimeRange) => void;
};

const { RangePicker } = DatePicker;
const DATE_TIME_FORMAT = 'YYYY-MM-DD HH:mm:ss';
const LOCAL_DATE_TIME_FORMAT = 'YYYY-MM-DDTHH:mm:ss';

export function DateTimeRangePicker({ value, onChange }: DateTimeRangePickerProps) {
  const pickerValue: [Dayjs, Dayjs] | null = value.from && value.to
    ? [dayjs(value.from), dayjs(value.to)]
    : null;
  const presets = [
    { label: t.today, value: [dayjs().startOf('day'), dayjs().endOf('day')] as [Dayjs, Dayjs] },
    { label: t.last24Hours, value: [dayjs().subtract(24, 'hour'), dayjs()] as [Dayjs, Dayjs] },
    { label: t.last7Days, value: [dayjs().subtract(7, 'day').startOf('day'), dayjs()] as [Dayjs, Dayjs] },
  ];

  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          borderRadius: 8,
          colorBgElevated: '#fbfcf8',
          colorBorder: '#b9c4bd',
          colorPrimary: '#0f766e',
          colorText: '#26231e',
          controlHeight: 38,
        },
      }}
    >
      <RangePicker
        className="sessionRangePicker"
        value={pickerValue}
        format={DATE_TIME_FORMAT}
        showTime={{
          format: 'HH:mm:ss',
          defaultOpenValue: [dayjs().startOf('day'), dayjs().endOf('day')],
        }}
        needConfirm
        presets={presets}
        placeholder={[t.rangeStart, t.rangeEnd]}
        allowClear
        onChange={dates => {
          if (!dates?.[0] || !dates[1]) {
            onChange({ from: '', to: '' });
            return;
          }
          onChange({
            from: dates[0].format(LOCAL_DATE_TIME_FORMAT),
            to: dates[1].format(LOCAL_DATE_TIME_FORMAT),
          });
        }}
      />
    </ConfigProvider>
  );
}
