package com.omniread.backend.store.smoke;

import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * 冒烟用的 mapper；语句在 {@code resources/mapper/SmokeNoteMapper.xml}。
 *
 * <p>XML 的 namespace 必须与这里的全限定名逐字一致，语句 id 必须与方法名逐字一致——
 * {@code Invalid bound statement} 九成出在这两处对不上。
 */
@Mapper
public interface SmokeNoteMapper {

    /** 幂等建表：SQLite 没有独立的迁移工具，一期就是启动时 {@code IF NOT EXISTS}。 */
    void createTable();

    /** 自增主键回填：SQLite 驱动支持 {@code useGeneratedKeys}，但要实测一次。 */
    int insert(SmokeNote note);

    SmokeNote findById(@Param("id") long id);

    List<SmokeNote> findAll();
}
