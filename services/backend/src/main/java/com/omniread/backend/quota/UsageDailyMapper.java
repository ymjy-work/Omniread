package com.omniread.backend.quota;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 每日问答计数（语句在 `resources/mapper/UsageDailyMapper.xml`）。 */
@Mapper
public interface UsageDailyMapper {

    /** 有则加一、无则插入。**占位与计数是同一条语句**，中间没有可乘之机。 */
    int bump(@Param("day") String day, @Param("userId") long userId);

    /** 没有这一行时返回 null（今天还没问过），与 0 是同一件事、但别让 SQL 假装它有行。 */
    Integer turns(@Param("day") String day, @Param("userId") long userId);

    /** 退还一轮：provider 故障那一轮不该吃掉额度。带着 `turns > 0` 的守卫，退不成负数。 */
    int refund(@Param("day") String day, @Param("userId") long userId);

    /** 只保留最近若干天；启动时清一次。 */
    int deleteBefore(@Param("day") String day);

    /** 停用账户时随会话与进度一起清理。 */
    int deleteByUserId(@Param("userId") long userId);
}
